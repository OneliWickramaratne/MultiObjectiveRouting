from __future__ import annotations

import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AmbulanceModel, HospitalModel, ICUBedModel, TransferRequestModel, UserModel
from app.services.resource_claim_service import claim_available_ambulance, claim_available_bed
from app.services.transfer_state_machine import (
    TRANSFER_ACCEPTED_WAITING_AMBULANCE,
    TRANSFER_PENDING_DESTINATION,
    transition_transfer_atomic,
)


class ResourceClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        with self.session_factory() as db:
            db.add_all(
                [
                    self._hospital("H1"),
                    self._hospital("H2"),
                    UserModel(id="U1", name="Admin", role="hospital_admin", hospital_id="H1"),
                    ICUBedModel(
                        id="B1",
                        hospital_id="H2",
                        bed_no="BED-01",
                        icu_type="general",
                        status="available",
                    ),
                    ICUBedModel(
                        id="B2",
                        hospital_id="H2",
                        bed_no="BED-02",
                        icu_type="general",
                        status="available",
                    ),
                    AmbulanceModel(
                        id="A1",
                        call_sign="Alpha",
                        base_hospital_id="H1",
                        status="available",
                        latitude=6.9,
                        longitude=79.8,
                    ),
                    AmbulanceModel(
                        id="A2",
                        call_sign="Bravo",
                        base_hospital_id="H2",
                        status="available",
                        latitude=6.91,
                        longitude=79.81,
                    ),
                    TransferRequestModel(
                        id="T1",
                        origin_hospital_id="H1",
                        destination_hospital_id="H2",
                        requested_by_user_id="U1",
                        status=TRANSFER_PENDING_DESTINATION,
                        patient_condition="trauma",
                        required_icu_type="general",
                        urgency_class="critical",
                        urgency_score=1.0,
                    ),
                ]
            )
            db.commit()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_beds_are_claimed_once_in_stable_order(self) -> None:
        with self.session_factory() as db:
            first = claim_available_bed(db, "H2")
            second = claim_available_bed(db, "H2")
            third = claim_available_bed(db, "H2")
            self.assertEqual(first.id if first else None, "B1")
            self.assertEqual(second.id if second else None, "B2")
            self.assertIsNone(third)

    def test_ranked_ambulance_claim_falls_through_to_next_available(self) -> None:
        with self.session_factory() as db:
            first = claim_available_ambulance(db, ["A1", "A2"])
            second = claim_available_ambulance(db, ["A1", "A2"])
            third = claim_available_ambulance(db, ["A1", "A2"])
            self.assertEqual(first, "A1")
            self.assertEqual(second, "A2")
            self.assertIsNone(third)

    def test_stale_transfer_cannot_be_accepted_twice(self) -> None:
        first_db: Session = self.session_factory()
        second_db: Session = self.session_factory()
        try:
            first = first_db.get(TransferRequestModel, "T1")
            second = second_db.get(TransferRequestModel, "T1")
            transition_transfer_atomic(first_db, first, TRANSFER_ACCEPTED_WAITING_AMBULANCE)
            first_db.commit()
            with self.assertRaises(HTTPException) as context:
                transition_transfer_atomic(second_db, second, TRANSFER_ACCEPTED_WAITING_AMBULANCE)
            self.assertEqual(context.exception.status_code, 409)
        finally:
            first_db.close()
            second_db.close()

    @staticmethod
    def _hospital(hospital_id: str) -> HospitalModel:
        return HospitalModel(
            id=hospital_id,
            name=f"Hospital {hospital_id}",
            latitude=6.9,
            longitude=79.8,
            icu_type="general",
            total_beds=2,
            occupied_beds=0,
        )


if __name__ == "__main__":
    unittest.main()
