from __future__ import annotations

from datetime import datetime
import json
import os

from app.auth import hash_password
from app.config import settings
from app.data_store import HOSPITALS
from app.database import SessionLocal
from app.models import AmbulanceModel, HospitalModel, ICUBedModel, PatientRecordModel, TransferRequestModel, UserModel


AMBULANCES_PER_HOSPITAL = 2
ACTIVE_TRANSFER_STATUSES = {
    "accepted_pending_ambulance",
    "ambulance_assigned",
    "ambulance_en_route_to_pickup",
    "patient_onboard",
    "en_route_to_destination",
}


def init_db() -> None:
    if settings.is_production:
        # Production schema and bootstrap data must be provisioned by reviewed
        # migrations and administrative workflows, never development seed code.
        return
    with SessionLocal() as db:
        if db.query(HospitalModel).count() == 0:
            for hospital in HOSPITALS:
                db.add(
                    HospitalModel(
                        id=hospital.id,
                        name=hospital.name,
                        latitude=hospital.latitude,
                        longitude=hospital.longitude,
                        icu_type=hospital.icu_types[0],
                        total_beds=hospital.total_beds,
                        occupied_beds=hospital.occupied_beds,
                        supports_trauma=hospital.supports_trauma,
                        supports_cardiac=hospital.supports_cardiac,
                        supports_neuro=hospital.supports_neuro,
                        supports_pediatric=hospital.supports_pediatric,
                        supports_maternity=hospital.supports_maternity,
                        has_ventilator_support=hospital.has_ventilator_support,
                    )
                )
        db.flush()
        _sync_hospital_reference_data(db)
        _ensure_icu_beds(db)

        if db.query(UserModel).count() == 0:
            db.add(UserModel(id="super-admin", name="Super Admin", role="super_admin"))
            for hospital in HOSPITALS:
                db.add(
                    UserModel(
                        id=f"hospital-{hospital.id}-admin",
                        name=f"{hospital.name} Admin",
                        role="hospital_admin",
                        hospital_id=hospital.id,
                    )
                )

        if db.query(AmbulanceModel).count() == 0:
            ambulances = [
                ("AMB-001", "Alpha 1", "1", 6.9169, 79.8684),
                ("AMB-002", "Bravo 2", "2", 6.8734, 79.8768),
                ("AMB-003", "Charlie 3", "4", 6.8894, 79.8895),
                ("AMB-004", "Delta 4", "6", 6.9149, 79.8508),
                ("AMB-005", "Echo 5", "7", 6.8919, 79.8692),
            ]
            for ambulance_id, call_sign, hospital_id, latitude, longitude in ambulances:
                db.add(
                    AmbulanceModel(
                        id=ambulance_id,
                        call_sign=call_sign,
                        base_hospital_id=hospital_id,
                        status="available",
                        latitude=latitude,
                        longitude=longitude,
                    )
                )
        db.flush()
        _ensure_hospital_ambulance_pool(db)

        for ambulance in db.query(AmbulanceModel).all():
            crew_user_id = f"ambulance-{ambulance.id.lower()}"
            if not db.get(UserModel, crew_user_id):
                db.add(
                    UserModel(
                        id=crew_user_id,
                        name=f"{ambulance.call_sign} Crew",
                        role="ambulance_crew",
                        ambulance_id=ambulance.id,
                    )
                )
        db.flush()
        development_password = os.getenv("DEV_SEED_PASSWORD")
        for user in db.query(UserModel).all():
            user.username = user.username or user.id
            if development_password and not user.password_hash:
                user.password_hash = hash_password(development_password)
                user.password_changed_at = datetime.utcnow()
        db.commit()


def _ensure_hospital_ambulance_pool(db) -> None:
    for hospital in HOSPITALS:
        existing = (
            db.query(AmbulanceModel)
            .filter(AmbulanceModel.base_hospital_id == hospital.id)
            .order_by(AmbulanceModel.id)
            .all()
        )
        active_ids = {
            row[0]
            for row in db.query(TransferRequestModel.ambulance_id)
            .filter(
                TransferRequestModel.ambulance_id.is_not(None),
                TransferRequestModel.status.in_(ACTIVE_TRANSFER_STATUSES),
            )
            .all()
        }
        active_existing = [ambulance for ambulance in existing if ambulance.id in active_ids]
        inactive_existing = [ambulance for ambulance in existing if ambulance.id not in active_ids]
        keepers = active_existing + inactive_existing[: max(AMBULANCES_PER_HOSPITAL - len(active_existing), 0)]
        keeper_ids = {ambulance.id for ambulance in keepers}
        for ambulance in existing:
            if ambulance.id in keeper_ids:
                continue
            db.query(TransferRequestModel).filter(
                TransferRequestModel.ambulance_id == ambulance.id,
                TransferRequestModel.status.not_in(ACTIVE_TRANSFER_STATUSES),
            ).update({TransferRequestModel.ambulance_id: None}, synchronize_session=False)
            db.query(UserModel).filter(UserModel.ambulance_id == ambulance.id).delete(synchronize_session=False)
            db.delete(ambulance)

        db.flush()
        existing_count = (
            db.query(AmbulanceModel)
            .filter(AmbulanceModel.base_hospital_id == hospital.id)
            .count()
        )
        for slot in range(existing_count + 1, AMBULANCES_PER_HOSPITAL + 1):
            ambulance_id = f"AMB-H{int(hospital.id):02d}-{slot:02d}"
            if db.get(AmbulanceModel, ambulance_id):
                continue
            offset = slot * 0.00025
            db.add(
                AmbulanceModel(
                    id=ambulance_id,
                    call_sign=f"{hospital.name.split()[0]} {slot}",
                    base_hospital_id=hospital.id,
                    status="available",
                    latitude=hospital.latitude + offset,
                    longitude=hospital.longitude + offset,
                )
            )
        for slot, ambulance in enumerate(
            db.query(AmbulanceModel)
            .filter(AmbulanceModel.base_hospital_id == hospital.id)
            .order_by(AmbulanceModel.id)
            .all(),
            start=1,
        ):
            ambulance.call_sign = f"{_hospital_unit_code(hospital.name)} Ambulance {slot}"


def _hospital_unit_code(name: str) -> str:
    replacements = ("Sri Lanka", "Hospital", "Teaching", "General", "Central", "for Women")
    normalized = name
    for text in replacements:
        normalized = normalized.replace(text, "")
    words = [word for word in normalized.split() if word]
    return "".join(word[0].upper() for word in words[:3]) or "H"


def _ensure_icu_beds(db) -> None:
    static_by_id = {hospital.id: hospital for hospital in HOSPITALS}
    for hospital in db.query(HospitalModel).order_by(HospitalModel.id).all():
        static = static_by_id.get(hospital.id)
        existing_count = db.query(ICUBedModel).filter(ICUBedModel.hospital_id == hospital.id).count()

        if existing_count == 0 and static:
            # Fresh hospital: seed each ICU ward with its own specialty type,
            # bed count, and occupancy — a hospital can run more than one ICU
            # specialty at once (e.g. a Trauma ICU and a Cardiac ICU).
            number = 0
            for ward_capacity in static.icu_capacity:
                ward_name = f"{ward_capacity.icu_type.replace(' ICU', '')} Ward"
                for seat in range(1, ward_capacity.total_beds + 1):
                    number += 1
                    bed_no = f"BED-{number:02d}"
                    status = "occupied" if seat <= ward_capacity.occupied_beds else "available"
                    bed = ICUBedModel(
                        id=f"H{hospital.id}-{bed_no}",
                        hospital_id=hospital.id,
                        bed_no=bed_no,
                        icu_type=ward_capacity.icu_type,
                        ward=ward_name,
                        status=status,
                        fhir_location_id=f"Location/H{hospital.id}-{bed_no}",
                        operational_status="occupied" if status == "occupied" else "available",
                    )
                    db.add(bed)
                    db.flush()
                    # A patient record is created below (once, for every
                    # occupied/reserved/transfer-assigned bed) by
                    # _ensure_realistic_patient — do not also create one here,
                    # or the two inserts collide on the same bed.
        elif existing_count < hospital.total_beds:
            # Legacy top-up path (e.g. hospital.total_beds increased on an
            # already-seeded database): fall back to the hospital's primary
            # type rather than guessing a ward split for pre-existing data.
            for number in range(existing_count + 1, hospital.total_beds + 1):
                bed_no = f"BED-{number:02d}"
                status = "occupied" if number <= hospital.occupied_beds else "available"
                bed = ICUBedModel(
                    id=f"H{hospital.id}-{bed_no}",
                    hospital_id=hospital.id,
                    bed_no=bed_no,
                    icu_type=hospital.icu_type,
                    ward="Ward A" if number <= max(hospital.total_beds // 2, 1) else "Ward B",
                    status=status,
                    fhir_location_id=f"Location/H{hospital.id}-{bed_no}",
                    operational_status="occupied" if status == "occupied" else "available",
                )
                db.add(bed)
                db.flush()

        beds = db.query(ICUBedModel).filter(ICUBedModel.hospital_id == hospital.id).all()
        for bed in beds:
            bed.fhir_location_id = bed.fhir_location_id or f"Location/{bed.id}"
            bed.operational_status = bed.operational_status or ("occupied" if bed.status == "occupied" else "available")
            if bed.status in {"occupied", "reserved", "transfer_assigned"}:
                _ensure_realistic_patient(db, hospital, bed)
        hospital.total_beds = len(beds)
        hospital.occupied_beds = sum(1 for bed in beds if bed.status != "available")


SYNTHETIC_PATIENTS = (
    ("Nadeesha Perera", 54, "female", "O+", "Severe community-acquired pneumonia", "respiratory support", "Ceftriaxone, azithromycin"),
    ("Dilan Fernando", 67, "male", "A+", "Acute coronary syndrome", "haemodynamic monitoring", "Aspirin, heparin, atorvastatin"),
    ("Tharushi Silva", 38, "female", "B+", "Post-operative abdominal sepsis", "critical but stable", "Meropenem, noradrenaline"),
    ("Kasun Jayasinghe", 46, "male", "O-", "Polytrauma with chest injury", "ventilated", "Fentanyl, tranexamic acid"),
    ("Fathima Rizwana", 59, "female", "AB+", "Acute ischaemic stroke", "neurological observation", "Clopidogrel, atorvastatin"),
    ("Suresh Kumar", 72, "male", "B-", "Acute kidney injury with sepsis", "renal support", "Piperacillin-tazobactam"),
    ("Imesha Wickramasinghe", 29, "female", "A-", "Severe dengue with shock", "fluid resuscitation", "Crystalloid infusion, paracetamol"),
    ("Ruwan Senanayake", 61, "male", "O+", "COPD exacerbation", "non-invasive ventilation", "Salbutamol, hydrocortisone"),
    ("Chamari Gunawardena", 43, "female", "B+", "Diabetic ketoacidosis", "metabolic stabilisation", "Insulin infusion, potassium chloride"),
    ("Mohamed Akeel", 56, "male", "A+", "Upper gastrointestinal bleeding", "close observation", "Pantoprazole infusion"),
    ("Sajini de Alwis", 34, "female", "AB-", "Post-operative neurosurgical care", "stable", "Levetiracetam, paracetamol"),
    ("Pradeep Bandara", 64, "male", "O+", "Cardiogenic pulmonary oedema", "cardiac support", "Furosemide, nitroglycerin"),
)


def _ensure_realistic_patient(db, hospital: HospitalModel, bed: ICUBedModel) -> None:
    """Backfill synthetic development records without replacing entered clinical values."""
    try:
        bed_number = int(bed.bed_no.split("-")[-1])
    except ValueError:
        bed_number = 1
    seed_index = (int(hospital.id) * 7 + bed_number - 1) % len(SYNTHETIC_PATIENTS)
    name, age, sex, blood_type, diagnosis, condition, medications = SYNTHETIC_PATIENTS[seed_index]
    patient = bed.patient
    if not patient:
        patient = PatientRecordModel(
            id=f"PAT-H{hospital.id}-{bed_number:03d}",
            hospital_id=hospital.id,
            bed_id=bed.id,
            patient_no=f"MRN-{int(hospital.id):02d}-{bed_number:04d}",
            patient_name=name,
            condition=condition,
        )
        db.add(patient)
        bed.patient = patient

    patient.patient_no = patient.patient_no or f"MRN-{int(hospital.id):02d}-{bed_number:04d}"
    if patient.patient_name.startswith("ICU Patient") or patient.patient_name == "Unnamed Patient":
        patient.patient_name = name
    patient.identifier_system = patient.identifier_system or "https://health.gov.lk/mrn"
    patient.identifier_value = patient.identifier_value or patient.patient_no
    patient.age = patient.age if patient.age is not None else age
    patient.date_of_birth = patient.date_of_birth or f"{2026 - patient.age:04d}-{(seed_index % 12) + 1:02d}-{(bed_number % 27) + 1:02d}"
    patient.sex = patient.sex or sex
    patient.blood_type = patient.blood_type or blood_type
    patient.condition = patient.condition if patient.condition not in {"under observation", ""} else condition
    patient.diagnosis = patient.diagnosis or diagnosis
    patient.vitals_json = patient.vitals_json or json.dumps(
        {
            "heart_rate": 76 + (seed_index * 5) % 48,
            "blood_pressure": f"{104 + seed_index * 3}/{64 + seed_index * 2}",
            "spo2": 91 + seed_index % 8,
            "temperature_c": round(36.5 + (seed_index % 5) * 0.3, 1),
        }
    )
    patient.medications_json = patient.medications_json or json.dumps(
        [item.strip() for item in medications.split(",")]
    )
    patient.allergies = patient.allergies or ("Penicillin" if seed_index % 5 == 0 else "No known drug allergies")
    patient.infection_risk = patient.infection_risk or ("contact precautions" if seed_index in {2, 5} else "standard")
    patient.emergency_contact = patient.emergency_contact or f"Family contact / 077 {2100000 + seed_index * 731 + bed_number:07d}"
    patient.next_of_kin = patient.next_of_kin or f"{name.split()[0]} family representative"
    patient.address = patient.address or f"Colombo District, Western Province"
    patient.notes = patient.notes or "Synthetic demonstration record for ICU workflow testing."
    patient.updated_at = datetime.utcnow()


def _sync_hospital_reference_data(db) -> None:
    """Keep map/reference fields current without overwriting admin-managed bed counts."""
    for hospital in HOSPITALS:
        stored = db.get(HospitalModel, hospital.id)
        if not stored:
            continue
        stored.name = hospital.name
        stored.latitude = hospital.latitude
        stored.longitude = hospital.longitude
        # icu_type on the hospital row is just a "primary" display label now —
        # a hospital's real specialty mix lives at the bed level (see
        # _ensure_icu_beds), where different wards can carry different types.
        stored.icu_type = hospital.icu_types[0]
        stored.supports_trauma = hospital.supports_trauma
        stored.supports_cardiac = hospital.supports_cardiac
        stored.supports_neuro = hospital.supports_neuro
        stored.supports_pediatric = hospital.supports_pediatric
        stored.supports_maternity = hospital.supports_maternity
        stored.has_ventilator_support = hospital.has_ventilator_support
        stored.updated_at = datetime.utcnow()

if __name__ == "__main__":
    init_db()
