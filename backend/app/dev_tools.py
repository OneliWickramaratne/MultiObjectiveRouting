from __future__ import annotations

from app.data_store import HOSPITALS
from app.database import SessionLocal
from app.models import AmbulanceModel, HospitalModel, TransferEventModel, TransferRequestModel


def reset_demo_state() -> None:
    with SessionLocal() as db:
        db.query(TransferEventModel).delete()
        db.query(TransferRequestModel).delete()
        hospitals = {
            hospital.id: hospital
            for hospital in db.query(HospitalModel).all()
        }
        for ambulance in db.query(AmbulanceModel).order_by(AmbulanceModel.id).all():
            ambulance.status = "available"
            base = hospitals.get(ambulance.base_hospital_id or "")
            if base:
                ambulance.latitude = base.latitude
                ambulance.longitude = base.longitude

        for seed_hospital in HOSPITALS:
            hospital = db.get(HospitalModel, seed_hospital.id)
            if hospital:
                hospital.name = seed_hospital.name
                hospital.latitude = seed_hospital.latitude
                hospital.longitude = seed_hospital.longitude
                hospital.total_beds = seed_hospital.total_beds
                hospital.occupied_beds = seed_hospital.occupied_beds
        db.commit()


if __name__ == "__main__":
    reset_demo_state()
    print("Demo transfers cleared, hospital beds restored, and ambulances parked at base.")
