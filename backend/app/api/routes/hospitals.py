from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.data_store import normalize_icu_type
from app.database import get_db
from app.models import HospitalModel
from app.schemas import HospitalSummary
from app.services.db_adapters import hospital_from_model, resolve_hospital_model

router = APIRouter()


def to_summary(hospital) -> HospitalSummary:
    return HospitalSummary(
        id=hospital.id,
        name=hospital.name,
        latitude=hospital.latitude,
        longitude=hospital.longitude,
        icu_types=list(hospital.icu_types),
        total_beds=hospital.total_beds,
        occupied_beds=hospital.occupied_beds,
        available_beds=hospital.available_beds,
        supports_trauma=hospital.supports_trauma,
        supports_cardiac=hospital.supports_cardiac,
        supports_neuro=hospital.supports_neuro,
        supports_pediatric=hospital.supports_pediatric,
        supports_maternity=hospital.supports_maternity,
        has_ventilator_support=hospital.has_ventilator_support,
    )


@router.get("", response_model=list[HospitalSummary])
def list_hospitals(
    icu_type: str | None = None,
    has_available_bed: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[HospitalSummary]:
    hospitals = [hospital_from_model(db, row) for row in db.query(HospitalModel).order_by(HospitalModel.id).all()]
    if icu_type:
        normalized_icu = normalize_icu_type(icu_type)
        hospitals = [hospital for hospital in hospitals if normalized_icu in hospital.icu_types]
    if has_available_bed:
        hospitals = [hospital for hospital in hospitals if hospital.available_beds > 0]
    return [to_summary(hospital) for hospital in hospitals]


@router.get("/{hospital_id}", response_model=HospitalSummary)
def get_hospital_detail(hospital_id: str, db: Session = Depends(get_db)) -> HospitalSummary:
    row = resolve_hospital_model(db, hospital_id)
    hospital = hospital_from_model(db, row) if row else None
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return to_summary(hospital)
