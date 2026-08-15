from __future__ import annotations


from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AmbulanceModel, ICUBedModel
from app.time_utils import utcnow



def claim_available_bed(
    db: Session,
    hospital_id: str,
    candidate_limit: int = 10,
) -> ICUBedModel | None:
    """Atomically reserve the first available bed, retrying if another request wins."""
    candidate_ids = db.scalars(
        select(ICUBedModel.id)
        .where(
            ICUBedModel.hospital_id == hospital_id,
            ICUBedModel.status == "available",
        )
        .order_by(ICUBedModel.bed_no)
        .limit(candidate_limit)
    ).all()

    for bed_id in candidate_ids:
        result = db.execute(
            update(ICUBedModel)
            .where(
                ICUBedModel.id == bed_id,
                ICUBedModel.status == "available",
            )
            .values(
                status="transfer_assigned",
                operational_status="reserved",
                status_reason="Reserved for accepted incoming transfer.",
                updated_at=utcnow(),
            ),
            execution_options={"synchronize_session": False},
        )
        if result.rowcount == 1:
            bed = db.get(ICUBedModel, bed_id)
            if bed:
                db.refresh(bed)
            return bed
    return None


def claim_available_ambulance(
    db: Session,
    ranked_ambulance_ids: list[str],
) -> str | None:
    """Atomically claim the highest-ranked ambulance that remains available."""
    for ambulance_id in ranked_ambulance_ids:
        result = db.execute(
            update(AmbulanceModel)
            .where(
                AmbulanceModel.id == ambulance_id,
                AmbulanceModel.status == "available",
            )
            .values(status="assigned", updated_at=utcnow()),
            execution_options={"synchronize_session": False},
        )
        if result.rowcount == 1:
            return ambulance_id
    return None
