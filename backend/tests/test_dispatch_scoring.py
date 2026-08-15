from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AmbulanceModel, HospitalModel
from app.services.dispatch_service import DispatchService


class UrgencyWeightTests(unittest.TestCase):
    def test_known_classes_map_to_their_documented_weights(self) -> None:
        weights = {
            "critical": 1.0,
            "high": 1.15,
            "moderate": 1.35,
            "low": 1.55,
        }
        for urgency_class, expected in weights.items():
            with self.subTest(urgency_class=urgency_class):
                self.assertEqual(DispatchService._urgency_weight(urgency_class), expected)

    def test_unrecognised_class_falls_back_rather_than_raising(self) -> None:
        self.assertEqual(DispatchService._urgency_weight("not-a-class"), 1.2)
        self.assertEqual(DispatchService._urgency_weight(""), 1.2)

    def test_more_urgent_classes_discount_travel_time_less(self) -> None:
        # Cost is summed, so the weight ordering is what makes a critical case
        # tolerate a longer pickup than a low-urgency one would.
        ordered = ["critical", "high", "moderate", "low"]
        weights = [DispatchService._urgency_weight(c) for c in ordered]
        self.assertEqual(weights, sorted(weights))


class StaleLocationPenaltyTests(unittest.TestCase):
    """The thresholds are exact, so the clock is frozen rather than sampled.

    Deriving `updated_at` from a live clock makes an age of exactly 10 minutes
    read as a hair over 10 by the time the penalty is computed, which would make
    the boundary cases flap.
    """

    NOW = datetime(2026, 8, 12, 9, 0, 0)

    def penalty_for_age(self, minutes: float | None) -> float:
        ambulance = AmbulanceModel(
            id="A", call_sign="A1", base_hospital_id="1", status="available",
            latitude=6.9, longitude=79.9,
        )
        ambulance.updated_at = None if minutes is None else self.NOW - timedelta(minutes=minutes)
        with patch("app.services.dispatch_service.utcnow", return_value=self.NOW):
            return DispatchService._stale_location_penalty(ambulance)

    def test_penalty_grows_with_the_age_of_the_last_fix(self) -> None:
        cases = [(0, 0.0), (5, 0.0), (10, 0.0), (11, 0.2), (30, 0.2), (31, 0.5), (120, 0.5)]
        for age_minutes, expected in cases:
            with self.subTest(age_minutes=age_minutes):
                self.assertEqual(self.penalty_for_age(age_minutes), expected)

    def test_missing_timestamp_is_penalised_but_not_worst_case(self) -> None:
        no_timestamp = self.penalty_for_age(None)
        self.assertEqual(no_timestamp, 0.35)
        self.assertLess(no_timestamp, self.penalty_for_age(31))

    def test_a_future_timestamp_does_not_produce_a_negative_penalty(self) -> None:
        # Clock skew between an ambulance tablet and the server must not turn
        # into a bonus that makes a stale unit look attractive.
        self.assertEqual(self.penalty_for_age(-45), 0.0)


class HaversineTests(unittest.TestCase):
    def test_identical_points_are_zero_apart(self) -> None:
        self.assertEqual(DispatchService._haversine_km(6.9271, 79.8612, 6.9271, 79.8612), 0.0)

    def test_one_degree_of_latitude_is_about_111_km(self) -> None:
        distance = DispatchService._haversine_km(6.0, 79.8612, 7.0, 79.8612)
        self.assertAlmostEqual(distance, 111.2, delta=0.5)

    def test_distance_is_symmetric(self) -> None:
        there = DispatchService._haversine_km(6.9271, 79.8612, 6.8410, 79.9730)
        back = DispatchService._haversine_km(6.8410, 79.9730, 6.9271, 79.8612)
        self.assertAlmostEqual(there, back, places=9)


class CoveragePenaltyTests(unittest.TestCase):
    """Leaving a base uncovered is the cost this penalty is meant to express."""

    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        self.db = self.session_factory()
        self.db.add(
            HospitalModel(
                id="1", name="Base Hospital", latitude=6.9271, longitude=79.8612,
                icu_type="general", total_beds=4, occupied_beds=0,
            )
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def add_ambulances(self, count: int, status: str = "available") -> AmbulanceModel:
        first = None
        for index in range(count):
            ambulance = AmbulanceModel(
                id=f"AMB-{status}-{index}", call_sign=f"C{index}", base_hospital_id="1",
                status=status, latitude=6.9271, longitude=79.8612,
            )
            self.db.add(ambulance)
            first = first or ambulance
        self.db.commit()
        return first

    def test_taking_the_last_available_unit_is_the_heaviest_penalty(self) -> None:
        ambulance = self.add_ambulances(1)
        self.assertEqual(DispatchService._coverage_penalty(self.db, ambulance), 1.0)

    def test_penalty_eases_as_more_units_remain_at_base(self) -> None:
        ambulance = self.add_ambulances(2)
        self.assertEqual(DispatchService._coverage_penalty(self.db, ambulance), 0.45)

    def test_a_well_staffed_base_is_barely_penalised(self) -> None:
        ambulance = self.add_ambulances(4)
        self.assertEqual(DispatchService._coverage_penalty(self.db, ambulance), 0.12)

    def test_unavailable_units_do_not_count_as_cover(self) -> None:
        # Three units at base, but two are busy: dispatching the free one still
        # empties the base and must be priced as such.
        self.add_ambulances(2, status="on_mission")
        ambulance = self.add_ambulances(1)
        self.assertEqual(DispatchService._coverage_penalty(self.db, ambulance), 1.0)

    def test_an_ambulance_with_no_base_is_penalised_without_a_query(self) -> None:
        ambulance = AmbulanceModel(
            id="AMB-NOBASE", call_sign="N1", base_hospital_id=None,
            status="available", latitude=6.9271, longitude=79.8612,
        )
        self.assertEqual(DispatchService._coverage_penalty(self.db, ambulance), 0.55)


if __name__ == "__main__":
    unittest.main()
