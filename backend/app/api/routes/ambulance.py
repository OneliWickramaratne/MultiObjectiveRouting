from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.auth import authenticate_access_token, consume_event_stream_ticket
from app.database import SessionLocal, get_db
from app.models import AmbulanceModel, ICUBedModel, TransferRequestModel
from app.schemas import AmbulanceMissionResponse, AmbulanceUpdateRequest
from app.api.routes.admin import (
    add_transfer_event,
    ambulance_to_summary,
    build_return_route_json,
    record_bed_lifecycle_event,
    sync_hospital_bed_counts,
    transfer_to_summary,
)
from app.services.route_motion_service import RouteTrack, bearing_degrees
from app.services.transfer_state_machine import (
    TRANSFER_COMPLETED,
    TRANSFER_EN_ROUTE_TO_DESTINATION,
    TRANSFER_EN_ROUTE_TO_PICKUP,
    transition_transfer_atomic,
)
from app.time_utils import utcnow

router = APIRouter()


def active_transfer_for_ambulance(db: Session, ambulance_id: str) -> TransferRequestModel | None:
    return (
        db.query(TransferRequestModel)
        .filter(
            TransferRequestModel.ambulance_id == ambulance_id,
            TransferRequestModel.status.in_(
                [
                    "ambulance_assigned",
                    "ambulance_en_route_to_pickup",
                    "arrived_at_pickup",
                    "en_route_to_destination",
                ]
            ),
        )
        .order_by(TransferRequestModel.updated_at.desc())
        .first()
    )


def mission_response(db: Session, ambulance: AmbulanceModel) -> AmbulanceMissionResponse:
    transfer = active_transfer_for_ambulance(db, ambulance.id)
    return_route_json = None if transfer else build_return_route_json(db, ambulance)
    return AmbulanceMissionResponse(
        ambulance=ambulance_to_summary(db, ambulance),
        active_transfer=transfer_to_summary(transfer) if transfer else None,
        return_route_json=return_route_json,
    )


@router.get("/mission", response_model=AmbulanceMissionResponse)
def get_active_mission(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AmbulanceMissionResponse:
    user, _ = authenticate_access_token(db, authorization)
    if user.role != "ambulance_crew" or not user.ambulance_id:
        raise HTTPException(status_code=403, detail="Ambulance crew access required")
    ambulance = db.get(AmbulanceModel, user.ambulance_id)
    if not ambulance:
        raise HTTPException(status_code=404, detail="Ambulance not found")

    return mission_response(db, ambulance)


@router.websocket("/telemetry")
async def telemetry_stream(websocket: WebSocket, ticket: str) -> None:
    try:
        with SessionLocal() as db:
            user = consume_event_stream_ticket(db, ticket)
            if user.role != "ambulance_crew" or not user.ambulance_id:
                raise HTTPException(status_code=403, detail="Ambulance crew access required")
            ambulance_id = user.ambulance_id
    except HTTPException:
        await websocket.accept()
        await websocket.close(code=4401, reason="Authentication required")
        return

    await websocket.accept()
    try:
        while True:
            with SessionLocal() as db:
                ambulance = db.get(AmbulanceModel, ambulance_id)
                if not ambulance:
                    await websocket.close(code=4404, reason="Ambulance not found")
                    return
                transfer = active_transfer_for_ambulance(db, ambulance.id)
                await websocket.send_json(
                    {
                        "kind": "ambulance_telemetry",
                        "ambulance": ambulance_to_summary(db, ambulance).model_dump(),
                        "active_transfer_id": transfer.id if transfer else None,
                        "active_transfer_status": transfer.status if transfer else None,
                        "server_time": utcnow().isoformat(),
                    }
                )
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return


@router.patch("/location", response_model=AmbulanceMissionResponse)
def update_location(
    request: AmbulanceUpdateRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AmbulanceMissionResponse:
    user, _ = authenticate_access_token(db, authorization)
    if user.role != "ambulance_crew" or not user.ambulance_id:
        raise HTTPException(status_code=403, detail="Ambulance crew access required")
    ambulance = db.get(AmbulanceModel, user.ambulance_id)
    if not ambulance:
        raise HTTPException(status_code=404, detail="Ambulance not found")
    previous_position = (ambulance.latitude, ambulance.longitude)
    if request.latitude is not None and request.longitude is not None:
        latitude, longitude = _map_match_location(db, ambulance, request.latitude, request.longitude)
        ambulance.latitude = latitude
        ambulance.longitude = longitude
        if request.heading_degrees is None:
            ambulance.heading_degrees = bearing_degrees(previous_position, (latitude, longitude))
    if request.status is not None:
        ambulance.status = request.status
    if request.heading_degrees is not None:
        ambulance.heading_degrees = request.heading_degrees
    if request.speed_kph is not None:
        ambulance.speed_kph = request.speed_kph
    ambulance.telemetry_updated_at = utcnow()
    ambulance.updated_at = utcnow()
    db.commit()
    return mission_response(db, ambulance)


def _map_match_location(
    db: Session,
    ambulance: AmbulanceModel,
    latitude: float,
    longitude: float,
) -> tuple[float, float]:
    transfer = active_transfer_for_ambulance(db, ambulance.id)
    if not transfer or not transfer.route_payload_json:
        return latitude, longitude
    route_name = (
        "pickup_route"
        if transfer.status in {"ambulance_assigned", "ambulance_en_route_to_pickup"}
        else "destination_route"
    )
    try:
        route_payload = json.loads(transfer.route_payload_json).get(route_name, {})
    except json.JSONDecodeError:
        return latitude, longitude
    track = RouteTrack.from_polyline(route_payload.get("polyline", []))
    if not track:
        return latitude, longitude
    projection = track.project(
        latitude,
        longitude,
        minimum_progress_m=max(ambulance.route_progress_m - 20, 0),
    )
    if projection.offset_m <= 80:
        ambulance.route_progress_m = max(ambulance.route_progress_m, projection.progress_m)
        ambulance.navigation_leg = "pickup" if route_name == "pickup_route" else "destination"
        return projection.latitude, projection.longitude
    ambulance.navigation_leg = "off_route"
    return latitude, longitude


@router.post("/mission/{transfer_id}/{action}", response_model=AmbulanceMissionResponse)
def update_mission_status(
    transfer_id: str,
    action: str,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AmbulanceMissionResponse:
    user, _ = authenticate_access_token(db, authorization)
    if user.role != "ambulance_crew" or not user.ambulance_id:
        raise HTTPException(status_code=403, detail="Ambulance crew access required")
    transfer = db.get(TransferRequestModel, transfer_id)
    if not transfer or transfer.ambulance_id != user.ambulance_id:
        raise HTTPException(status_code=404, detail="Mission not found")
    ambulance = db.get(AmbulanceModel, user.ambulance_id)

    status_map = {
        "start-pickup": (
            TRANSFER_EN_ROUTE_TO_PICKUP,
            "en_route",
            "ambulance_en_route_to_pickup",
            "Ambulance started toward pickup hospital.",
        ),
        "arrive-pickup": (
            TRANSFER_EN_ROUTE_TO_DESTINATION,
            "transporting",
            "patient_onboard",
            "Patient is onboard; ambulance started toward receiving hospital.",
        ),
        "complete": (
            TRANSFER_COMPLETED,
            "available",
            "transfer_completed",
            "Patient delivered; transfer completed. Ambulance is available and returning to base if unassigned.",
        ),
    }
    if action not in status_map:
        raise HTTPException(status_code=422, detail="Unknown mission action")
    transfer_status, ambulance_status, event_type, message = status_map[action]
    transition_transfer_atomic(db, transfer, transfer_status)
    transfer.updated_at = utcnow()
    ambulance.status = ambulance_status
    ambulance.speed_kph = 0.0
    ambulance.route_progress_m = 0.0
    ambulance.telemetry_updated_at = utcnow()
    if action == "start-pickup":
        ambulance.navigation_leg = "pickup"
    elif action == "arrive-pickup":
        ambulance.latitude = transfer.pickup_latitude or ambulance.latitude
        ambulance.longitude = transfer.pickup_longitude or ambulance.longitude
        ambulance.navigation_leg = "destination"
    elif action == "complete":
        ambulance.latitude = transfer.dropoff_latitude or ambulance.latitude
        ambulance.longitude = transfer.dropoff_longitude or ambulance.longitude
        ambulance.navigation_leg = "return_to_base"
        if transfer.assigned_bed_id:
            bed = db.get(ICUBedModel, transfer.assigned_bed_id)
            if bed:
                previous_status = bed.status
                bed.status = "occupied"
                bed.status_reason = "Patient arrived by ambulance and occupied assigned ICU bed."
                bed.updated_at = utcnow()
                if bed.patient:
                    bed.patient.identifier_system = bed.patient.identifier_system or "urn:ietf:rfc:3986"
                    bed.patient.identifier_value = transfer.patient_identifier_value or bed.patient.identifier_value
                    bed.patient.date_of_birth = transfer.patient_date_of_birth or bed.patient.date_of_birth
                    bed.patient.patient_name = transfer.patient_name or bed.patient.patient_name
                    bed.patient.age = transfer.patient_age
                    bed.patient.sex = transfer.patient_sex
                    bed.patient.blood_type = transfer.patient_blood_type
                    bed.patient.condition = transfer.patient_condition
                    bed.patient.diagnosis = transfer.patient_diagnosis
                    bed.patient.vitals_json = transfer.patient_vitals_json
                    bed.patient.medications_json = transfer.patient_medications_json
                    bed.patient.allergies = transfer.patient_allergies
                    bed.patient.infection_risk = transfer.patient_infection_risk
                    bed.patient.isolation_required = transfer.patient_isolation_required
                    bed.patient.emergency_contact = transfer.patient_emergency_contact
                    bed.patient.transfer_id = transfer.id
                    bed.patient.notes = transfer.notes
                    bed.patient.updated_at = utcnow()
                record_bed_lifecycle_event(
                    db,
                    bed,
                    previous_status,
                    bed.status,
                    user,
                    "Transfer completed; patient arrived in assigned ICU bed.",
                    bed.patient.id if bed.patient else None,
                    transfer.id,
                )
                sync_hospital_bed_counts(db, bed.hospital_id)
    ambulance.updated_at = utcnow()
    add_transfer_event(
        db,
        transfer,
        user,
        event_type,
        message,
        {"ambulance_id": ambulance.id, "ambulance_status": ambulance.status},
    )
    db.commit()
    return mission_response(db, ambulance)
