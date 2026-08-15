from __future__ import annotations

import json
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AmbulanceModel, HospitalModel, TransferRequestModel, UserModel
from app.services.dispatch_service import DispatchService
from app.services.traffic_model_service import TrafficPrediction
from app.services.transfer_state_machine import (
    TRANSFER_ACCEPTED_WAITING_AMBULANCE,
    TRANSFER_AMBULANCE_ASSIGNED,
)

ORIGIN_LAT, ORIGIN_LON = 6.9271, 79.8612
DESTINATION_LAT, DESTINATION_LON = 6.8410, 79.9730


class StubTrafficModel:
    def predict(self, origin, destination, when=None) -> TrafficPrediction:
        return TrafficPrediction(
            distance_km=12.0,
            static_duration_seconds=900.0,
            predicted_duration_seconds=1100.0,
            congestion_ratio=1.25,
            risk_score=0.4,
            model_used="stub_model",
        )


class StubGraph:
    """Returns no geometry, pinning scoring to the deterministic direct path."""

    def route(self, *args, **kwargs):
        return None

    def route_coordinates(self, **kwargs):
        return None


class AutoAssignTests(unittest.TestCase):
    """The orchestration path: rank, atomically claim, then record the decision."""

    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)()

        self.db.add_all(
            [
                HospitalModel(
                    id="1", name="Origin Hospital", latitude=ORIGIN_LAT, longitude=ORIGIN_LON,
                    icu_type="general", total_beds=6, occupied_beds=2,
                ),
                HospitalModel(
                    id="2", name="Destination Hospital",
                    latitude=DESTINATION_LAT, longitude=DESTINATION_LON,
                    icu_type="general", total_beds=6, occupied_beds=1,
                ),
                UserModel(
                    id="requester", username="requester", name="Requester",
                    role="hospital_admin", hospital_id="1", is_active=True,
                    failed_login_count=0,
                ),
            ]
        )
        self.db.commit()

        self.service = DispatchService()
        self.service.traffic_model = StubTrafficModel()
        self.service.osm_graph = StubGraph()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def add_ambulance(
        self,
        identifier: str,
        *,
        latitude: float,
        longitude: float,
        status: str = "available",
        base_hospital_id: str | None = "1",
    ) -> AmbulanceModel:
        ambulance = AmbulanceModel(
            id=identifier, call_sign=identifier, base_hospital_id=base_hospital_id,
            status=status, latitude=latitude, longitude=longitude,
        )
        self.db.add(ambulance)
        self.db.commit()
        return ambulance

    def add_transfer(self, urgency_class: str = "critical") -> TransferRequestModel:
        transfer = TransferRequestModel(
            id="T-1", origin_hospital_id="1", destination_hospital_id="2",
            requested_by_user_id="requester", status=TRANSFER_ACCEPTED_WAITING_AMBULANCE,
            patient_condition="respiratory", required_icu_type="general",
            urgency_class=urgency_class, urgency_score=0.9,
        )
        self.db.add(transfer)
        self.db.commit()
        return transfer

    def dispatch_payload(self, transfer: TransferRequestModel) -> dict:
        return json.loads(transfer.route_payload_json)["dispatch"]

    def test_returns_nothing_when_no_ambulance_is_available(self) -> None:
        self.add_ambulance("AMB-BUSY", latitude=ORIGIN_LAT, longitude=ORIGIN_LON, status="assigned")
        transfer = self.add_transfer()
        self.assertIsNone(self.service.auto_assign(self.db, transfer))
        self.assertIsNone(transfer.ambulance_id)
        self.assertEqual(transfer.status, TRANSFER_ACCEPTED_WAITING_AMBULANCE)

    def test_returns_nothing_when_a_hospital_is_missing(self) -> None:
        self.add_ambulance("AMB-1", latitude=ORIGIN_LAT, longitude=ORIGIN_LON)
        transfer = self.add_transfer()
        transfer.destination_hospital_id = "does-not-exist"
        self.db.commit()
        self.assertIsNone(self.service.auto_assign(self.db, transfer))

    def test_assigns_the_nearer_unit_and_marks_it_taken(self) -> None:
        self.add_ambulance("AMB-NEAR", latitude=ORIGIN_LAT + 0.002, longitude=ORIGIN_LON)
        self.add_ambulance("AMB-FAR", latitude=ORIGIN_LAT + 0.25, longitude=ORIGIN_LON)
        transfer = self.add_transfer()

        result = self.service.auto_assign(self.db, transfer)

        self.assertIsNotNone(result)
        self.assertEqual(result.ambulance.id, "AMB-NEAR")
        self.assertEqual(result.ambulance.status, "assigned")
        self.assertEqual(transfer.ambulance_id, "AMB-NEAR")
        self.assertEqual(transfer.status, TRANSFER_AMBULANCE_ASSIGNED)

    def test_a_busy_unit_is_never_selected_even_when_closest(self) -> None:
        self.add_ambulance(
            "AMB-BUSY", latitude=ORIGIN_LAT, longitude=ORIGIN_LON, status="on_mission"
        )
        self.add_ambulance("AMB-FREE", latitude=ORIGIN_LAT + 0.05, longitude=ORIGIN_LON)
        transfer = self.add_transfer()

        result = self.service.auto_assign(self.db, transfer)

        self.assertEqual(result.ambulance.id, "AMB-FREE")
        busy = self.db.get(AmbulanceModel, "AMB-BUSY")
        self.assertEqual(busy.status, "on_mission")

    def test_pickup_and_dropoff_coordinates_are_recorded(self) -> None:
        self.add_ambulance("AMB-1", latitude=ORIGIN_LAT, longitude=ORIGIN_LON)
        transfer = self.add_transfer()

        self.service.auto_assign(self.db, transfer)

        self.assertEqual((transfer.pickup_latitude, transfer.pickup_longitude), (ORIGIN_LAT, ORIGIN_LON))
        self.assertEqual(
            (transfer.dropoff_latitude, transfer.dropoff_longitude),
            (DESTINATION_LAT, DESTINATION_LON),
        )

    def test_the_decision_is_recorded_for_audit(self) -> None:
        self.add_ambulance("AMB-1", latitude=ORIGIN_LAT, longitude=ORIGIN_LON)
        transfer = self.add_transfer()

        result = self.service.auto_assign(self.db, transfer)
        dispatch = self.dispatch_payload(transfer)

        self.assertEqual(dispatch["model"], "coverage_risk_eta_dispatch_v2")
        self.assertAlmostEqual(dispatch["score"], round(result.score, 4), places=4)
        self.assertTrue(dispatch["explanation"])
        self.assertIn("score_components", dispatch)
        payload = json.loads(transfer.route_payload_json)
        self.assertIn("pickup_route", payload)
        self.assertIn("destination_route", payload)

    def test_candidate_rankings_are_capped_and_ordered(self) -> None:
        for index in range(7):
            self.add_ambulance(
                f"AMB-{index}", latitude=ORIGIN_LAT + index * 0.01, longitude=ORIGIN_LON
            )
        transfer = self.add_transfer()

        self.service.auto_assign(self.db, transfer)
        rankings = self.dispatch_payload(transfer)["candidate_rankings"]

        self.assertLessEqual(len(rankings), 5)
        scores = [entry["score"] for entry in rankings]
        self.assertEqual(scores, sorted(scores), "rankings must be best-first")

    def test_only_the_eight_nearest_units_are_scored(self) -> None:
        # Twelve candidates, but the shortlist is capped at eight before scoring.
        for index in range(12):
            self.add_ambulance(
                f"AMB-{index:02d}", latitude=ORIGIN_LAT + index * 0.02, longitude=ORIGIN_LON
            )
        transfer = self.add_transfer()

        result = self.service.auto_assign(self.db, transfer)

        self.assertIsNotNone(result)
        # The four most distant units cannot have been considered at all.
        considered = {entry["ambulance_id"] for entry in self.dispatch_payload(transfer)["candidate_rankings"]}
        for far in ["AMB-08", "AMB-09", "AMB-10", "AMB-11"]:
            self.assertNotIn(far, considered)

    def test_a_unit_based_at_the_origin_is_preferred_over_an_equally_placed_visitor(self) -> None:
        self.add_ambulance("AMB-HOME", latitude=ORIGIN_LAT, longitude=ORIGIN_LON, base_hospital_id="1")
        self.add_ambulance("AMB-VISIT", latitude=ORIGIN_LAT, longitude=ORIGIN_LON, base_hospital_id="2")
        transfer = self.add_transfer()

        result = self.service.auto_assign(self.db, transfer)

        self.assertEqual(result.ambulance.id, "AMB-HOME")
        self.assertLess(result.base_match_bonus, 0.0)

    def test_assignment_is_not_repeated_for_an_already_claimed_fleet(self) -> None:
        self.add_ambulance("AMB-1", latitude=ORIGIN_LAT, longitude=ORIGIN_LON)
        first = self.add_transfer()
        self.assertIsNotNone(self.service.auto_assign(self.db, first))

        second = TransferRequestModel(
            id="T-2", origin_hospital_id="1", destination_hospital_id="2",
            requested_by_user_id="requester", status=TRANSFER_ACCEPTED_WAITING_AMBULANCE,
            patient_condition="cardiac", required_icu_type="general",
            urgency_class="high", urgency_score=0.7,
        )
        self.db.add(second)
        self.db.commit()

        self.assertIsNone(self.service.auto_assign(self.db, second))
        self.assertIsNone(second.ambulance_id)


if __name__ == "__main__":
    unittest.main()
