from __future__ import annotations

from sqlalchemy.orm import Session

from app.data_store import Hospital, IcuWardCapacity
from app.data_store import get_hospital as get_static_hospital
from app.models import HospitalModel, ICUBedModel


def hospital_from_model(db: Session, hospital: HospitalModel) -> Hospital:
    # A hospital's real ICU specialty mix lives at the bed level (each bed
    # row carries its own icu_type), so per-ward capacity is derived from
    # actual bed records rather than the hospital's single "primary" type —
    # this is what lets a hospital run more than one ICU specialty at once.
    beds = db.query(ICUBedModel).filter(ICUBedModel.hospital_id == hospital.id).all()
    capacity_by_type: dict[str, list[int]] = {}
    for bed in beds:
        counts = capacity_by_type.setdefault(bed.icu_type, [0, 0])
        counts[0] += 1
        if bed.status != "available":
            counts[1] += 1
    icu_capacity = tuple(
        IcuWardCapacity(icu_type=icu_type, total_beds=total, occupied_beds=occupied)
        for icu_type, (total, occupied) in capacity_by_type.items()
    ) or (IcuWardCapacity(icu_type=hospital.icu_type, total_beds=hospital.total_beds, occupied_beds=hospital.occupied_beds),)
    return Hospital(
        id=hospital.id,
        name=hospital.name,
        latitude=hospital.latitude,
        longitude=hospital.longitude,
        icu_capacity=icu_capacity,
        supports_trauma=hospital.supports_trauma,
        supports_cardiac=hospital.supports_cardiac,
        supports_neuro=hospital.supports_neuro,
        supports_pediatric=hospital.supports_pediatric,
        supports_maternity=hospital.supports_maternity,
        has_ventilator_support=hospital.has_ventilator_support,
    )


def get_hospital_from_list(hospitals: list[Hospital], hospital_id: str) -> Hospital | None:
    normalized = hospital_id.strip().lower()
    return next(
        (
            hospital
            for hospital in hospitals
            if hospital.id == normalized
            or normalized in hospital.aliases
            or hospital.name.lower() == normalized
        ),
        None,
    )


def resolve_hospital_model(db, hospital_id: str) -> HospitalModel | None:
    row = db.get(HospitalModel, hospital_id)
    if row:
        return row
    static = get_static_hospital(hospital_id)
    if static:
        return db.get(HospitalModel, static.id)
    return None
