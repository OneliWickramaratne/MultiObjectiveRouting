from __future__ import annotations

import json
import time
import unittest
from datetime import datetime

from app.models import AmbulanceModel, HospitalModel, TransferRequestModel
from app.services.fleet_simulation_service import (
    FleetSimulationService,
    MotionProgress,
)
from app.services.route_motion_service import RouteTrack


def ambulance(latitude: float = 6.9271, longitude: float = 79.8612) -> AmbulanceModel:
    return AmbulanceModel(
        id="AMB-SIM", call_sign="SIM-1", base_hospital_id="1",
        status="available", latitude=latitude, longitude=longitude,
    )


def hospital(latitude: float = 6.9271, longitude: float = 79.8612) -> HospitalModel:
    return HospitalModel(
        id="1", name="Base", latitude=latitude, longitude=longitude,
        icu_type="general", total_beds=4, occupied_beds=0,
    )


class RoutePayloadParsingTests(unittest.TestCase):
    """This parses data written by another service, so it must not raise."""

    def payload_for(self, raw: str | None, route_name: str = "pickup_route") -> dict:
        transfer = TransferRequestModel(id="T1", status="ambulance_assigned")
        transfer.route_payload_json = raw
        return FleetSimulationService._route_payload(transfer, route_name)

    def test_reads_the_requested_route_out_of_the_payload(self) -> None:
        raw = json.dumps({"pickup_route": {"polyline": [[1.0, 2.0]]}, "destination_route": {}})
        self.assertEqual(self.payload_for(raw), {"polyline": [[1.0, 2.0]]})

    def test_missing_and_empty_payloads_yield_an_empty_route(self) -> None:
        for raw in [None, "", "{}"]:
            with self.subTest(raw=raw):
                self.assertEqual(self.payload_for(raw), {})

    def test_malformed_json_is_swallowed_rather_than_crashing_the_tick(self) -> None:
        # One bad row must not take down the simulation loop for the whole fleet.
        for raw in ["not json", "{unclosed", "[1,2,"]:
            with self.subTest(raw=raw):
                self.assertEqual(self.payload_for(raw), {})

    def test_a_route_of_the_wrong_shape_is_rejected(self) -> None:
        for value in ["a string", 42, [1, 2, 3], None]:
            with self.subTest(value=value):
                raw = json.dumps({"pickup_route": value})
                self.assertEqual(self.payload_for(raw), {})

    def test_asking_for_an_absent_route_name_is_safe(self) -> None:
        raw = json.dumps({"pickup_route": {"polyline": []}})
        self.assertEqual(self.payload_for(raw, "destination_route"), {})


class AtBaseTests(unittest.TestCase):
    def test_an_ambulance_on_the_pad_counts_as_at_base(self) -> None:
        self.assertTrue(FleetSimulationService._is_at_base(ambulance(), hospital()))

    def test_a_few_metres_away_still_counts_as_at_base(self) -> None:
        # ~2 m north, inside the 4 m tolerance.
        self.assertTrue(
            FleetSimulationService._is_at_base(ambulance(latitude=6.92711800), hospital())
        )

    def test_across_the_street_does_not_count(self) -> None:
        # ~55 m north.
        self.assertFalse(
            FleetSimulationService._is_at_base(ambulance(latitude=6.92760), hospital())
        )


class ParkAndStationaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FleetSimulationService()

    def test_parking_snaps_the_unit_to_base_and_frees_it(self) -> None:
        unit = ambulance(latitude=6.95, longitude=79.90)
        unit.route_progress_m = 4200.0
        unit.navigation_leg = "destination"
        unit.speed_kph = 48.0
        base = hospital()
        self.service._motion[unit.id] = "sentinel"

        self.service._park_at_base(unit, base)

        self.assertEqual((unit.latitude, unit.longitude), (base.latitude, base.longitude))
        self.assertEqual(unit.speed_kph, 0.0)
        self.assertEqual(unit.route_progress_m, 0.0)
        self.assertIsNone(unit.navigation_leg)
        self.assertEqual(unit.status, "available")
        self.assertNotIn(unit.id, self.service._motion, "parking must drop stale motion state")

    def test_going_stationary_stops_the_unit_without_moving_it(self) -> None:
        unit = ambulance(latitude=6.95, longitude=79.90)
        unit.speed_kph = 33.0
        now = datetime(2026, 8, 12, 9, 0, 0)

        self.service._set_stationary(unit, "pickup", now)

        self.assertEqual(unit.speed_kph, 0.0)
        self.assertEqual(unit.navigation_leg, "pickup")
        self.assertEqual(unit.telemetry_updated_at, now)
        self.assertEqual((unit.latitude, unit.longitude), (6.95, 79.90))


class AdvanceMotionTests(unittest.TestCase):
    """Movement is distance-based, so a stalled or jumpy tick must stay bounded."""

    def setUp(self) -> None:
        self.service = FleetSimulationService()
        # A straight north-running line, roughly 1.1 km.
        self.track = RouteTrack.from_polyline(
            [[6.9271, 79.8612], [6.9371, 79.8612]]
        )
        self.now = datetime(2026, 8, 12, 9, 0, 0)

    def motion(self, progress_m: float = 0.0, speed_mps: float = 10.0, age: float = 1.0) -> MotionProgress:
        return MotionProgress(
            route_key="pickup:1",
            track=self.track,
            progress_m=progress_m,
            speed_mps=speed_mps,
            navigation_leg="pickup",
            last_tick=time.monotonic() - age,
        )

    def test_progress_advances_and_position_is_written_back(self) -> None:
        unit = ambulance()
        motion = self.motion()
        self.service._advance_motion(unit, motion, self.now)
        self.assertGreater(motion.progress_m, 0.0)
        self.assertEqual(unit.route_progress_m, motion.progress_m)
        self.assertEqual(unit.navigation_leg, "pickup")
        self.assertEqual(unit.updated_at, self.now)

    def test_a_long_stall_does_not_teleport_the_unit(self) -> None:
        # A paused thread must not translate into a kilometre-long jump.
        unit = ambulance()
        motion = self.motion(speed_mps=20.0, age=600.0)
        self.service._advance_motion(unit, motion, self.now)
        self.assertLessEqual(motion.progress_m, 20.0 * 1.5)

    def test_progress_never_runs_past_the_end_of_the_route(self) -> None:
        unit = ambulance()
        motion = self.motion(progress_m=self.track.total_m - 1.0, speed_mps=500.0)
        self.service._advance_motion(unit, motion, self.now)
        self.assertLessEqual(motion.progress_m, self.track.total_m)

    def test_arriving_reports_a_stopped_vehicle(self) -> None:
        unit = ambulance()
        motion = self.motion(progress_m=self.track.total_m, speed_mps=15.0)
        self.service._advance_motion(unit, motion, self.now)
        self.assertEqual(unit.speed_kph, 0.0)

    def test_mid_route_reports_a_moving_vehicle(self) -> None:
        unit = ambulance()
        motion = self.motion(progress_m=100.0, speed_mps=10.0)
        self.service._advance_motion(unit, motion, self.now)
        self.assertGreater(unit.speed_kph, 0.0)


if __name__ == "__main__":
    unittest.main()
