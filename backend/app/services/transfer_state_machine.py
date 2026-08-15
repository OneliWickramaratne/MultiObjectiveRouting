from __future__ import annotations


from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import TransferRequestModel
from app.time_utils import utcnow



TRANSFER_PENDING_DESTINATION = "pending_destination_acceptance"
TRANSFER_ACCEPTED_WAITING_AMBULANCE = "accepted_pending_ambulance"
TRANSFER_REJECTED = "rejected"
TRANSFER_AMBULANCE_ASSIGNED = "ambulance_assigned"
TRANSFER_EN_ROUTE_TO_PICKUP = "ambulance_en_route_to_pickup"
TRANSFER_EN_ROUTE_TO_DESTINATION = "en_route_to_destination"
TRANSFER_COMPLETED = "completed"
TRANSFER_CANCELLED = "cancelled"


ALLOWED_TRANSFER_TRANSITIONS: dict[str, set[str]] = {
    TRANSFER_PENDING_DESTINATION: {
        TRANSFER_ACCEPTED_WAITING_AMBULANCE,
        TRANSFER_REJECTED,
        TRANSFER_CANCELLED,
    },
    TRANSFER_ACCEPTED_WAITING_AMBULANCE: {
        TRANSFER_AMBULANCE_ASSIGNED,
        TRANSFER_CANCELLED,
    },
    TRANSFER_AMBULANCE_ASSIGNED: {
        TRANSFER_EN_ROUTE_TO_PICKUP,
        TRANSFER_CANCELLED,
    },
    TRANSFER_EN_ROUTE_TO_PICKUP: {
        TRANSFER_EN_ROUTE_TO_DESTINATION,
        TRANSFER_CANCELLED,
    },
    TRANSFER_EN_ROUTE_TO_DESTINATION: {
        TRANSFER_COMPLETED,
        TRANSFER_CANCELLED,
    },
    TRANSFER_REJECTED: set(),
    TRANSFER_COMPLETED: set(),
    TRANSFER_CANCELLED: set(),
}


def validate_transfer_transition(current_status: str, next_status: str) -> None:
    if current_status == next_status:
        return
    allowed = ALLOWED_TRANSFER_TRANSITIONS.get(current_status, set())
    if next_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Invalid transfer transition from {current_status} to {next_status}",
        )


def transition_transfer(transfer: TransferRequestModel, next_status: str) -> None:
    validate_transfer_transition(transfer.status, next_status)
    transfer.status = next_status


def transition_transfer_atomic(
    db: Session,
    transfer: TransferRequestModel,
    next_status: str,
) -> None:
    """Apply a state transition only if the persisted status still matches."""
    current_status = transfer.status
    validate_transfer_transition(current_status, next_status)
    result = db.execute(
        update(TransferRequestModel)
        .where(
            TransferRequestModel.id == transfer.id,
            TransferRequestModel.status == current_status,
        )
        .values(status=next_status, updated_at=utcnow()),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        db.refresh(transfer)
        raise HTTPException(
            status_code=409,
            detail=f"Transfer changed concurrently; current status is {transfer.status}",
        )
    transfer.status = next_status
    transfer.updated_at = utcnow()
