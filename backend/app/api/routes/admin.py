from __future__ import annotations

import json
import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload

from app.auth import authenticate_access_token, consume_event_stream_ticket, require_hospital_scope, require_super_admin
from app.database import SessionLocal, get_db
from app.models import (
    AmbulanceModel,
    AuditLogModel,
    BedLifecycleEventModel,
    HospitalModel,
    ICUBedModel,
    PatientRecordModel,
    TransferEventModel,
    TransferRequestModel,
    UserModel,
)
from app.schemas import (
    AmbulanceSummary,
    AmbulanceUpdateRequest,
    BedLifecycleEventSummary,
    CapacityForecastSummary,
    DashboardSummary,
    ICUBedSummary,
    ICUBedUpdateRequest,
    HospitalSummary,
    HospitalUpdateRequest,
    PatientRecordSummary,
    SimulationAnalyticsSummary,
    SimulationScenarioRequest,
    TransferActionRequest,
    TransferCreateRequest,
    TransferEventSummary,
    TransferSummary,
    UrgencyPredictionRequest,
    UserSummary,
)
from app.services.capacity_forecast_service import CapacityForecastService
from app.services.resource_claim_service import claim_available_bed
from app.services.dispatch_service import DispatchService
from app.services.sensitive_data import redact_sensitive
from app.services.simulation_analytics_service import SimulationAnalyticsService
from app.services.transfer_state_machine import (
    TRANSFER_ACCEPTED_WAITING_AMBULANCE,
    TRANSFER_PENDING_DESTINATION,
    TRANSFER_REJECTED,
    transition_transfer_atomic,
)
from app.services.urgency_service import UrgencyService
from app.time_utils import utcnow

router = APIRouter()

capacity_forecast_service = CapacityForecastService()
simulation_analytics_service = SimulationAnalyticsService()


def user_can_see_transfer(user: UserModel, transfer: TransferRequestModel | None) -> bool:
    if not transfer:
        return False
    if user.role == "super_admin":
        return True
    if user.role == "hospital_admin":
        return user.hospital_id in {transfer.origin_hospital_id, transfer.destination_hospital_id}
    if user.role == "ambulance_crew":
        return user.ambulance_id == transfer.ambulance_id
    return False


def available_beds(hospital: HospitalModel) -> int:
    bed_count = len(hospital.icu_beds)
    if bed_count:
        return sum(1 for bed in hospital.icu_beds if bed.status == "available")
    return max(hospital.total_beds - hospital.occupied_beds, 0)


def hospital_to_summary(hospital: HospitalModel) -> HospitalSummary:
    bed_types = sorted({bed.icu_type for bed in hospital.icu_beds}) or [hospital.icu_type]
    return HospitalSummary(
        id=hospital.id,
        name=hospital.name,
        latitude=hospital.latitude,
        longitude=hospital.longitude,
        icu_types=bed_types,
        total_beds=hospital.total_beds,
        occupied_beds=hospital.occupied_beds,
        available_beds=available_beds(hospital),
        supports_trauma=hospital.supports_trauma,
        supports_cardiac=hospital.supports_cardiac,
        supports_neuro=hospital.supports_neuro,
        supports_pediatric=hospital.supports_pediatric,
        supports_maternity=hospital.supports_maternity,
        has_ventilator_support=hospital.has_ventilator_support,
    )


def build_return_route_json(db: Session, ambulance: AmbulanceModel) -> str | None:
    # An ambulance that just finished a mission stays "available" while the
    # fleet simulator quietly drives it back to base — this reconstructs that
    # trip so the dashboard/network map can draw it, not just the crew view.
    if ambulance.status != "available" or not ambulance.base_hospital_id:
        return None
    base = db.get(HospitalModel, ambulance.base_hospital_id)
    if not base:
        return None
    if abs(ambulance.latitude - base.latitude) + abs(ambulance.longitude - base.longitude) < 0.00003:
        return None
    return json.dumps(
        DispatchService.route_payload_for_coordinates(
            start=(ambulance.latitude, ambulance.longitude),
            end=(base.latitude, base.longitude),
            urgency_class="moderate",
            fallback_source="return_to_base_polyline",
        )
    )


def ambulance_to_summary(db: Session, ambulance: AmbulanceModel) -> AmbulanceSummary:
    return AmbulanceSummary(
        id=ambulance.id,
        call_sign=ambulance.call_sign,
        base_hospital_id=ambulance.base_hospital_id,
        status=ambulance.status,
        latitude=ambulance.latitude,
        longitude=ambulance.longitude,
        crew_contact=ambulance.crew_contact,
        heading_degrees=ambulance.heading_degrees,
        speed_kph=ambulance.speed_kph,
        route_progress_m=ambulance.route_progress_m,
        navigation_leg=ambulance.navigation_leg,
        telemetry_updated_at=ambulance.telemetry_updated_at.isoformat() if ambulance.telemetry_updated_at else None,
        return_route_json=build_return_route_json(db, ambulance),
    )


def parse_json_payload(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def patient_to_summary(patient: PatientRecordModel) -> PatientRecordSummary:
    return PatientRecordSummary(
        id=patient.id,
        patient_no=patient.patient_no,
        patient_name=patient.patient_name,
        identifier_system=patient.identifier_system,
        identifier_value=patient.identifier_value,
        date_of_birth=patient.date_of_birth,
        age=patient.age,
        sex=patient.sex,
        blood_type=patient.blood_type,
        condition=patient.condition,
        diagnosis=patient.diagnosis,
        vitals=parse_json_payload(patient.vitals_json, None),
        medications=parse_json_payload(patient.medications_json, []),
        allergies=patient.allergies,
        infection_risk=patient.infection_risk,
        isolation_required=patient.isolation_required,
        emergency_contact=patient.emergency_contact,
        next_of_kin=patient.next_of_kin,
        address=patient.address,
        transfer_id=patient.transfer_id,
        notes=patient.notes,
        admitted_at=patient.admitted_at.isoformat(),
        updated_at=patient.updated_at.isoformat(),
    )


def icu_bed_to_summary(bed: ICUBedModel) -> ICUBedSummary:
    return ICUBedSummary(
        id=bed.id,
        hospital_id=bed.hospital_id,
        bed_no=bed.bed_no,
        icu_type=bed.icu_type,
        ward=bed.ward,
        status=bed.status,
        fhir_location_id=bed.fhir_location_id,
        operational_status=bed.operational_status,
        status_reason=bed.status_reason,
        patient=patient_to_summary(bed.patient) if bed.patient else None,
        updated_at=bed.updated_at.isoformat(),
    )


def sync_hospital_bed_counts(db: Session, hospital_id: str) -> None:
    hospital = db.get(HospitalModel, hospital_id)
    if not hospital:
        return
    hospital.total_beds = db.query(ICUBedModel).filter(ICUBedModel.hospital_id == hospital_id).count()
    hospital.occupied_beds = (
        db.query(ICUBedModel)
        .filter(ICUBedModel.hospital_id == hospital_id, ICUBedModel.status != "available")
        .count()
    )
    hospital.updated_at = utcnow()


def record_bed_lifecycle_event(
    db: Session,
    bed: ICUBedModel,
    previous_status: str | None,
    new_status: str,
    user: UserModel | None,
    reason: str | None = None,
    patient_id: str | None = None,
    transfer_id: str | None = None,
) -> None:
    if previous_status == new_status and not reason:
        return
    db.add(
        BedLifecycleEventModel(
            id=str(uuid4()),
            bed_id=bed.id,
            hospital_id=bed.hospital_id,
            actor_user_id=user.id if user else None,
            previous_status=previous_status,
            new_status=new_status,
            reason=reason,
            patient_id=patient_id,
            transfer_id=transfer_id,
        )
    )


def reserve_transfer_bed(db: Session, transfer: TransferRequestModel) -> ICUBedModel:
    bed = claim_available_bed(db, transfer.destination_hospital_id)
    if not bed:
        raise HTTPException(status_code=409, detail="Destination hospital has no available ICU beds")
    previous_status = "available"
    transfer.assigned_bed_id = bed.id
    patient = bed.patient
    if not patient:
        patient = PatientRecordModel(
            id=str(uuid4()),
            hospital_id=bed.hospital_id,
            bed_id=bed.id,
            patient_no=f"TR-{transfer.id[:8]}",
            patient_name=transfer.patient_name or "Incoming transfer patient",
            identifier_system="urn:ietf:rfc:3986",
            identifier_value=transfer.patient_identifier_value,
            date_of_birth=transfer.patient_date_of_birth,
            condition=transfer.patient_condition,
            diagnosis=transfer.patient_diagnosis,
            vitals_json=transfer.patient_vitals_json,
            medications_json=transfer.patient_medications_json,
            infection_risk=transfer.patient_infection_risk,
            isolation_required=transfer.patient_isolation_required,
            transfer_id=transfer.id,
        )
        db.add(patient)
        db.flush()
    patient.patient_no = patient.patient_no or f"TR-{transfer.id[:8]}"
    patient.patient_name = transfer.patient_name or patient.patient_name
    patient.identifier_system = patient.identifier_system or "urn:ietf:rfc:3986"
    patient.identifier_value = transfer.patient_identifier_value or patient.identifier_value
    patient.date_of_birth = transfer.patient_date_of_birth or patient.date_of_birth
    patient.age = transfer.patient_age
    patient.sex = transfer.patient_sex
    patient.blood_type = transfer.patient_blood_type
    patient.condition = transfer.patient_condition
    patient.diagnosis = transfer.patient_diagnosis
    patient.vitals_json = transfer.patient_vitals_json
    patient.medications_json = transfer.patient_medications_json
    patient.allergies = transfer.patient_allergies
    patient.infection_risk = transfer.patient_infection_risk
    patient.isolation_required = transfer.patient_isolation_required
    patient.emergency_contact = transfer.patient_emergency_contact
    patient.transfer_id = transfer.id
    patient.notes = transfer.notes
    patient.updated_at = utcnow()
    record_bed_lifecycle_event(
        db,
        bed,
        previous_status,
        bed.status,
        None,
        "Bed reserved for incoming transfer.",
        patient.id,
        transfer.id,
    )
    sync_hospital_bed_counts(db, bed.hospital_id)
    return bed


def transfer_to_summary(transfer: TransferRequestModel) -> TransferSummary:
    return TransferSummary(
        id=transfer.id,
        origin_hospital_id=transfer.origin_hospital_id,
        destination_hospital_id=transfer.destination_hospital_id,
        status=transfer.status,
        patient_name=transfer.patient_name,
        patient_age=transfer.patient_age,
        patient_sex=transfer.patient_sex,
        patient_blood_type=transfer.patient_blood_type,
        patient_allergies=transfer.patient_allergies,
        patient_emergency_contact=transfer.patient_emergency_contact,
        patient_identifier_value=transfer.patient_identifier_value,
        patient_date_of_birth=transfer.patient_date_of_birth,
        patient_diagnosis=transfer.patient_diagnosis,
        patient_vitals=parse_json_payload(transfer.patient_vitals_json, None),
        patient_medications=parse_json_payload(transfer.patient_medications_json, []),
        patient_infection_risk=transfer.patient_infection_risk,
        patient_isolation_required=transfer.patient_isolation_required,
        handover=parse_json_payload(transfer.handover_json, None),
        patient_condition=transfer.patient_condition,
        required_icu_type=transfer.required_icu_type,
        urgency_class=transfer.urgency_class,
        urgency_score=transfer.urgency_score,
        ventilator_required=transfer.ventilator_required,
        ambulance_id=transfer.ambulance_id,
        notes=transfer.notes,
        route_payload_json=transfer.route_payload_json,
        assigned_bed_id=transfer.assigned_bed_id,
        pickup_latitude=transfer.pickup_latitude,
        pickup_longitude=transfer.pickup_longitude,
        dropoff_latitude=transfer.dropoff_latitude,
        dropoff_longitude=transfer.dropoff_longitude,
        created_at=transfer.created_at.isoformat(),
        updated_at=transfer.updated_at.isoformat(),
    )


def bed_lifecycle_to_summary(event: BedLifecycleEventModel) -> BedLifecycleEventSummary:
    return BedLifecycleEventSummary(
        id=event.id,
        bed_id=event.bed_id,
        hospital_id=event.hospital_id,
        actor_user_id=event.actor_user_id,
        previous_status=event.previous_status,
        new_status=event.new_status,
        reason=event.reason,
        patient_id=event.patient_id,
        transfer_id=event.transfer_id,
        created_at=event.created_at.isoformat(),
    )


def transfer_event_to_summary(event: TransferEventModel) -> TransferEventSummary:
    return TransferEventSummary(
        id=event.id,
        transfer_id=event.transfer_id,
        actor_user_id=event.actor_user_id,
        event_type=event.event_type,
        status=event.status,
        message=event.message,
        details_json=event.details_json,
        created_at=event.created_at.isoformat(),
    )


def audit(db: Session, user: UserModel, action: str, entity_type: str, entity_id: str, details: dict | None = None) -> None:
    db.add(
        AuditLogModel(
            id=str(uuid4()),
            actor_user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details_json=json.dumps(redact_sensitive(details or {})),
        )
    )


def add_transfer_event(
    db: Session,
    transfer: TransferRequestModel,
    user: UserModel | None,
    event_type: str,
    message: str,
    details: dict | None = None,
) -> None:
    db.add(
        TransferEventModel(
            id=str(uuid4()),
            transfer_id=transfer.id,
            actor_user_id=user.id if user else None,
            event_type=event_type,
            status=transfer.status,
            message=message,
            details_json=json.dumps(redact_sensitive(details or {})),
        )
    )


def require_transfer_scope(user: UserModel, transfer: TransferRequestModel) -> None:
    if user.role == "super_admin":
        return
    if user.role == "hospital_admin" and user.hospital_id in {
        transfer.origin_hospital_id,
        transfer.destination_hospital_id,
    }:
        return
    if user.role == "ambulance_crew" and user.ambulance_id == transfer.ambulance_id:
        return
    raise HTTPException(status_code=403, detail="Transfer scope required")


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> DashboardSummary:
    user, _ = authenticate_access_token(db, authorization)
    if user.role == "super_admin":
        hospitals = db.query(HospitalModel).order_by(HospitalModel.id).all()
        ambulances = db.query(AmbulanceModel).order_by(AmbulanceModel.id).all()
        transfers = db.query(TransferRequestModel).order_by(TransferRequestModel.created_at.desc()).all()
    else:
        hospitals = db.query(HospitalModel).filter(HospitalModel.id == user.hospital_id).all()
        ambulances = db.query(AmbulanceModel).filter(AmbulanceModel.base_hospital_id == user.hospital_id).all()
        transfers = (
            db.query(TransferRequestModel)
            .filter(
                (TransferRequestModel.origin_hospital_id == user.hospital_id)
                | (TransferRequestModel.destination_hospital_id == user.hospital_id)
            )
            .order_by(TransferRequestModel.created_at.desc())
            .all()
        )
    return DashboardSummary(
        hospitals=[hospital_to_summary(hospital) for hospital in hospitals],
        ambulances=[ambulance_to_summary(db, ambulance) for ambulance in ambulances],
        transfers=[transfer_to_summary(transfer) for transfer in transfers],
    )


@router.get("/capacity/forecast", response_model=CapacityForecastSummary)
def capacity_forecast(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> CapacityForecastSummary:
    user, _ = authenticate_access_token(db, authorization)
    forecasts = capacity_forecast_service.forecast_network(db)
    if user.role != "super_admin":
        forecasts = [forecast for forecast in forecasts if forecast.hospital_id == user.hospital_id]
    if forecasts:
        worst_point = max(
            (point for forecast in forecasts for point in forecast.points),
            key=lambda point: point.pressure_score,
        )
        network_level = worst_point.pressure_level
        network_score = worst_point.pressure_score
    else:
        network_level = "stable"
        network_score = 0.0
    if network_level == "critical":
        network_action = "Network pressure is critical. Divert non-critical transfers and open surge capacity."
    elif network_level == "high":
        network_action = "Network pressure is high. Prioritize critical transfers and fast bed turnover."
    elif network_level == "elevated":
        network_action = "Network pressure is elevated. Prefer hospitals with stronger 6h availability."
    else:
        network_action = "Network capacity is stable. Continue normal risk-aware dispatch."
    return CapacityForecastSummary(
        generated_at=utcnow().isoformat(),
        network_pressure_level=network_level,
        network_pressure_score=network_score,
        network_recommended_action=network_action,
        hospitals=[
            {
                "hospital_id": forecast.hospital_id,
                "hospital_name": forecast.hospital_name,
                "total_beds": forecast.total_beds,
                "current_available_beds": forecast.current_available_beds,
                "current_occupied_beds": forecast.current_occupied_beds,
                "inbound_transfers": forecast.inbound_transfers,
                "expected_discharges_12h": forecast.expected_discharges_12h,
                "expected_cleaning_recoveries_12h": forecast.expected_cleaning_recoveries_12h,
                "points": [
                    {
                        "horizon_hours": point.horizon_hours,
                        "predicted_available_beds": point.predicted_available_beds,
                        "predicted_occupied_beds": point.predicted_occupied_beds,
                        "pressure_score": point.pressure_score,
                        "pressure_level": point.pressure_level,
                    }
                    for point in forecast.points
                ],
                "recommended_action": forecast.recommended_action,
            }
            for forecast in forecasts
        ],
    )


@router.post("/simulation/run", response_model=SimulationAnalyticsSummary)
def run_simulation(
    request: SimulationScenarioRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> SimulationAnalyticsSummary:
    user, _ = authenticate_access_token(db, authorization)
    forecasts = capacity_forecast_service.forecast_network(db)
    if user.role != "super_admin":
        forecasts = [forecast for forecast in forecasts if forecast.hospital_id == user.hospital_id]
    result = simulation_analytics_service.run(
        db=db,
        forecasts=forecasts,
        scenario=request.scenario,
        duration_hours=request.duration_hours,
        intensity=request.intensity,
    )
    audit(
        db,
        user,
        "simulation_run",
        "analytics",
        result["scenario"],
        {
            "duration_hours": request.duration_hours,
            "intensity": request.intensity,
            "network_pressure_level": result["network_pressure_level"],
            "simulated_transfers": result["simulated_transfers"],
        },
    )
    db.commit()
    return result


@router.get("/events/stream")
def stream_admin_events(
    ticket: str,
) -> StreamingResponse:
    with SessionLocal() as db:
        user = consume_event_stream_ticket(db, ticket)
        user_snapshot = {
            "id": user.id,
            "role": user.role,
            "hospital_id": user.hospital_id,
            "ambulance_id": user.ambulance_id,
        }

    async def event_generator():
        last_transfer_event_at = utcnow()
        last_bed_event_at = utcnow()
        yield "event: connected\ndata: {}\n\n"
        while True:
            emitted = False
            with SessionLocal() as db:
                user = UserModel(
                    id=user_snapshot["id"],
                    name=user_snapshot["id"],
                    role=user_snapshot["role"],
                    hospital_id=user_snapshot["hospital_id"],
                    ambulance_id=user_snapshot["ambulance_id"],
                )
                transfer_events = (
                    db.query(TransferEventModel)
                    .filter(TransferEventModel.created_at > last_transfer_event_at)
                    .order_by(TransferEventModel.created_at.asc())
                    .limit(50)
                    .all()
                )
                for event in transfer_events:
                    transfer = db.get(TransferRequestModel, event.transfer_id)
                    last_transfer_event_at = max(last_transfer_event_at, event.created_at)
                    if not user_can_see_transfer(user, transfer):
                        continue
                    payload = {
                        "kind": "transfer_event",
                        "event": transfer_event_to_summary(event).model_dump(),
                        "transfer": transfer_to_summary(transfer).model_dump() if transfer else None,
                    }
                    emitted = True
                    yield f"event: transfer_event\ndata: {json.dumps(payload)}\n\n"

                bed_events = (
                    db.query(BedLifecycleEventModel)
                    .filter(BedLifecycleEventModel.created_at > last_bed_event_at)
                    .order_by(BedLifecycleEventModel.created_at.asc())
                    .limit(50)
                    .all()
                )
                for event in bed_events:
                    last_bed_event_at = max(last_bed_event_at, event.created_at)
                    if user_snapshot["role"] != "super_admin" and event.hospital_id != user_snapshot["hospital_id"]:
                        continue
                    payload = {
                        "kind": "bed_lifecycle_event",
                        "event": bed_lifecycle_to_summary(event).model_dump(),
                    }
                    emitted = True
                    yield f"event: bed_lifecycle_event\ndata: {json.dumps(payload)}\n\n"
            if not emitted:
                yield "event: heartbeat\ndata: {}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/users", response_model=list[UserSummary])
def list_users(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> list[UserSummary]:
    user, _ = authenticate_access_token(db, authorization)
    require_super_admin(user)
    users = db.query(UserModel).order_by(UserModel.role, UserModel.id).all()
    return [
        UserSummary(
            id=item.id,
            name=item.name,
            role=item.role,
            hospital_id=item.hospital_id,
            ambulance_id=item.ambulance_id,
        )
        for item in users
    ]


@router.get("/transfers/{transfer_id}/events", response_model=list[TransferEventSummary])
def list_transfer_events(
    transfer_id: str,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> list[TransferEventSummary]:
    user, _ = authenticate_access_token(db, authorization)
    transfer = db.get(TransferRequestModel, transfer_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    require_transfer_scope(user, transfer)
    events = (
        db.query(TransferEventModel)
        .filter(TransferEventModel.transfer_id == transfer_id)
        .order_by(TransferEventModel.created_at.asc())
        .all()
    )
    return [transfer_event_to_summary(event) for event in events]


@router.patch("/hospitals/{hospital_id}", response_model=HospitalSummary)
def update_hospital(
    hospital_id: str,
    request: HospitalUpdateRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> HospitalSummary:
    user, _ = authenticate_access_token(db, authorization)
    require_hospital_scope(user, hospital_id)
    hospital = db.get(HospitalModel, hospital_id)
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")

    changes = request.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(hospital, key, value)
    if hospital.occupied_beds > hospital.total_beds:
        raise HTTPException(status_code=422, detail="Occupied beds cannot exceed total beds")
    hospital.updated_at = utcnow()
    audit(db, user, "hospital_update", "hospital", hospital_id, changes)
    db.commit()
    db.refresh(hospital)
    return hospital_to_summary(hospital)


@router.get("/hospitals/{hospital_id}/icu-beds", response_model=list[ICUBedSummary])
def list_icu_beds(
    hospital_id: str,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> list[ICUBedSummary]:
    user, _ = authenticate_access_token(db, authorization)
    require_hospital_scope(user, hospital_id)
    beds = (
        db.query(ICUBedModel)
        .filter(ICUBedModel.hospital_id == hospital_id)
        .order_by(ICUBedModel.icu_type, ICUBedModel.bed_no)
        .all()
    )
    return [icu_bed_to_summary(bed) for bed in beds]


@router.get("/icu-census", response_model=list[ICUBedSummary])
def list_icu_census(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> list[ICUBedSummary]:
    """Return the complete patient-bearing ICU census in the caller's scope."""
    user, _ = authenticate_access_token(db, authorization)
    query = (
        db.query(ICUBedModel)
        .options(selectinload(ICUBedModel.patient))
        .join(PatientRecordModel, PatientRecordModel.bed_id == ICUBedModel.id)
    )
    if user.role == "hospital_admin" and user.hospital_id:
        query = query.filter(ICUBedModel.hospital_id == user.hospital_id)
    elif user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Hospital or super admin access required")
    beds = query.order_by(ICUBedModel.hospital_id, ICUBedModel.icu_type, ICUBedModel.bed_no).all()
    return [icu_bed_to_summary(bed) for bed in beds]


@router.get("/icu-beds/{bed_id}/lifecycle", response_model=list[BedLifecycleEventSummary])
def list_bed_lifecycle(
    bed_id: str,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> list[BedLifecycleEventSummary]:
    user, _ = authenticate_access_token(db, authorization)
    bed = db.get(ICUBedModel, bed_id)
    if not bed:
        raise HTTPException(status_code=404, detail="ICU bed not found")
    require_hospital_scope(user, bed.hospital_id)
    events = (
        db.query(BedLifecycleEventModel)
        .filter(BedLifecycleEventModel.bed_id == bed_id)
        .order_by(BedLifecycleEventModel.created_at.desc())
        .limit(100)
        .all()
    )
    return [bed_lifecycle_to_summary(event) for event in events]


@router.patch("/icu-beds/{bed_id}", response_model=ICUBedSummary)
def update_icu_bed(
    bed_id: str,
    request: ICUBedUpdateRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> ICUBedSummary:
    user, _ = authenticate_access_token(db, authorization)
    bed = db.get(ICUBedModel, bed_id)
    if not bed:
        raise HTTPException(status_code=404, detail="ICU bed not found")
    require_hospital_scope(user, bed.hospital_id)

    changes = request.model_dump(exclude_unset=True)
    previous_status = bed.status
    previous_patient_id = bed.patient.id if bed.patient else None
    patient_removed_this_request = False
    if request.clear_patient and bed.patient:
        db.delete(bed.patient)
        patient_removed_this_request = True
        bed.status = "available"
        bed.status_reason = request.status_reason or "Patient removed from bed."
    elif request.patient_name or request.patient_no or request.patient_condition:
        patient = bed.patient
        if not patient:
            patient = PatientRecordModel(
                id=str(uuid4()),
                hospital_id=bed.hospital_id,
                bed_id=bed.id,
                patient_no=request.patient_no or f"PAT-{bed.bed_no}",
                patient_name=request.patient_name or "Unnamed Patient",
                identifier_system="urn:ietf:rfc:3986",
                identifier_value=request.patient_identifier_value,
                date_of_birth=request.patient_date_of_birth,
                age=request.patient_age,
                sex=request.patient_sex,
                blood_type=request.patient_blood_type,
                condition=request.patient_condition or "under observation",
                diagnosis=request.diagnosis,
                vitals_json=json.dumps(request.vitals) if request.vitals is not None else None,
                medications_json=json.dumps(request.medications) if request.medications is not None else None,
                allergies=request.allergies,
                infection_risk=request.infection_risk,
                isolation_required=bool(request.isolation_required),
                emergency_contact=request.emergency_contact,
                next_of_kin=request.next_of_kin,
                address=request.address,
            )
            db.add(patient)
            db.flush()
        patient.patient_no = request.patient_no or patient.patient_no
        patient.patient_name = request.patient_name or patient.patient_name
        patient.identifier_system = patient.identifier_system or "urn:ietf:rfc:3986"
        patient.identifier_value = request.patient_identifier_value if request.patient_identifier_value is not None else patient.identifier_value
        patient.date_of_birth = request.patient_date_of_birth if request.patient_date_of_birth is not None else patient.date_of_birth
        patient.age = request.patient_age if request.patient_age is not None else patient.age
        patient.sex = request.patient_sex if request.patient_sex is not None else patient.sex
        patient.blood_type = request.patient_blood_type if request.patient_blood_type is not None else patient.blood_type
        patient.condition = request.patient_condition or patient.condition
        patient.diagnosis = request.diagnosis if request.diagnosis is not None else patient.diagnosis
        patient.vitals_json = json.dumps(request.vitals) if request.vitals is not None else patient.vitals_json
        patient.medications_json = json.dumps(request.medications) if request.medications is not None else patient.medications_json
        patient.allergies = request.allergies if request.allergies is not None else patient.allergies
        patient.infection_risk = request.infection_risk if request.infection_risk is not None else patient.infection_risk
        patient.isolation_required = request.isolation_required if request.isolation_required is not None else patient.isolation_required
        patient.emergency_contact = request.emergency_contact if request.emergency_contact is not None else patient.emergency_contact
        patient.next_of_kin = request.next_of_kin if request.next_of_kin is not None else patient.next_of_kin
        patient.address = request.address if request.address is not None else patient.address
        patient.notes = request.notes if request.notes is not None else patient.notes
        patient.updated_at = utcnow()
        bed.status = "occupied"
        bed.status_reason = request.status_reason or "Patient assigned to ICU bed."
    elif request.status:
        bed.status = request.status
        bed.status_reason = request.status_reason
        if bed.status != "occupied" and bed.patient:
            db.delete(bed.patient)
            patient_removed_this_request = True

    bed.updated_at = utcnow()
    record_bed_lifecycle_event(
        db,
        bed,
        previous_status,
        bed.status,
        user,
        request.status_reason,
        None if patient_removed_this_request else (bed.patient.id if bed.patient else previous_patient_id),
        bed.patient.transfer_id if bed.patient else None,
    )
    sync_hospital_bed_counts(db, bed.hospital_id)
    audit(db, user, "icu_bed_update", "icu_bed", bed.id, changes)
    db.commit()
    db.refresh(bed)
    return icu_bed_to_summary(bed)


@router.get("/ambulances", response_model=list[AmbulanceSummary])
def list_ambulances(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> list[AmbulanceSummary]:
    user, _ = authenticate_access_token(db, authorization)
    query = db.query(AmbulanceModel)
    if user.role != "super_admin":
        query = query.filter(AmbulanceModel.base_hospital_id == user.hospital_id)
    return [ambulance_to_summary(db, ambulance) for ambulance in query.order_by(AmbulanceModel.id).all()]


@router.patch("/ambulances/{ambulance_id}", response_model=AmbulanceSummary)
def update_ambulance(
    ambulance_id: str,
    request: AmbulanceUpdateRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AmbulanceSummary:
    user, _ = authenticate_access_token(db, authorization)
    ambulance = db.get(AmbulanceModel, ambulance_id)
    if not ambulance:
        raise HTTPException(status_code=404, detail="Ambulance not found")
    if user.role != "super_admin" and ambulance.base_hospital_id != user.hospital_id:
        raise HTTPException(status_code=403, detail="Ambulance scope required")

    changes = request.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(ambulance, key, value)
    ambulance.updated_at = utcnow()
    audit(db, user, "ambulance_update", "ambulance", ambulance_id, changes)
    db.commit()
    db.refresh(ambulance)
    return ambulance_to_summary(db, ambulance)


@router.post("/transfers", response_model=TransferSummary)
def create_transfer_request(
    request: TransferCreateRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> TransferSummary:
    user, _ = authenticate_access_token(db, authorization)
    require_hospital_scope(user, request.origin_hospital_id)
    if not db.get(HospitalModel, request.destination_hospital_id):
        raise HTTPException(status_code=404, detail="Destination hospital not found")

    urgency = UrgencyService().predict(
        UrgencyPredictionRequest(
            **request.patient_condition.model_dump(),
            required_icu_type=request.required_icu_type,
        )
    )
    handover_packet = {
        "patient": {
            "identifier": request.patient_identifier_value,
            "name": request.patient_name,
            "date_of_birth": request.patient_date_of_birth,
            "age": request.patient_age,
            "sex": request.patient_sex,
            "blood_type": request.patient_blood_type,
            "emergency_contact": request.patient_emergency_contact,
        },
        "clinical": {
            "condition": request.patient_condition.model_dump(),
            "diagnosis": request.patient_diagnosis,
            "vitals": request.patient_vitals or {},
            "medications": request.patient_medications or [],
            "allergies": request.patient_allergies,
            "infection_risk": request.patient_infection_risk,
            "isolation_required": request.patient_isolation_required,
            "handover_notes": request.handover_notes,
        },
        "transfer": {
            "origin_hospital_id": request.origin_hospital_id,
            "destination_hospital_id": request.destination_hospital_id,
            "required_icu_type": request.required_icu_type,
        },
    }
    transfer = TransferRequestModel(
        id=str(uuid4()),
        origin_hospital_id=request.origin_hospital_id,
        destination_hospital_id=request.destination_hospital_id,
        requested_by_user_id=user.id,
        status=TRANSFER_PENDING_DESTINATION,
        patient_name=request.patient_name,
        patient_age=request.patient_age,
        patient_sex=request.patient_sex,
        patient_blood_type=request.patient_blood_type,
        patient_allergies=request.patient_allergies,
        patient_emergency_contact=request.patient_emergency_contact,
        patient_identifier_value=request.patient_identifier_value,
        patient_date_of_birth=request.patient_date_of_birth,
        patient_diagnosis=request.patient_diagnosis,
        patient_vitals_json=json.dumps(request.patient_vitals) if request.patient_vitals is not None else None,
        patient_medications_json=json.dumps(request.patient_medications) if request.patient_medications is not None else None,
        patient_infection_risk=request.patient_infection_risk,
        patient_isolation_required=request.patient_isolation_required,
        handover_json=json.dumps(handover_packet),
        patient_condition=request.patient_condition.condition_type,
        required_icu_type=request.required_icu_type,
        urgency_class=urgency.urgency_class,
        urgency_score=urgency.urgency_score,
        ventilator_required=request.patient_condition.ventilator_required,
        notes=request.notes,
    )
    db.add(transfer)
    db.flush()
    audit(db, user, "transfer_created", "transfer", transfer.id, request.model_dump())
    add_transfer_event(
        db,
        transfer,
        user,
        "transfer_created",
        "Transfer request created and sent to receiving hospital.",
        {
            "origin_hospital_id": transfer.origin_hospital_id,
            "destination_hospital_id": transfer.destination_hospital_id,
            "required_icu_type": transfer.required_icu_type,
            "urgency_class": transfer.urgency_class,
            "urgency_score": transfer.urgency_score,
        },
    )
    db.commit()
    db.refresh(transfer)
    return transfer_to_summary(transfer)


@router.post("/transfers/{transfer_id}/accept", response_model=TransferSummary)
def accept_transfer(
    transfer_id: str,
    request: TransferActionRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> TransferSummary:
    user, _ = authenticate_access_token(db, authorization)
    transfer = db.get(TransferRequestModel, transfer_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    require_hospital_scope(user, transfer.destination_hospital_id)
    if transfer.status != TRANSFER_PENDING_DESTINATION:
        raise HTTPException(status_code=409, detail=f"Transfer is already {transfer.status}")

    origin = db.get(HospitalModel, transfer.origin_hospital_id)
    destination = db.get(HospitalModel, transfer.destination_hospital_id)
    if not origin or not destination:
        raise HTTPException(status_code=404, detail="Transfer hospital not found")
    transition_transfer_atomic(db, transfer, TRANSFER_ACCEPTED_WAITING_AMBULANCE)
    transfer.notes = request.notes or transfer.notes
    transfer.updated_at = utcnow()
    reserved_bed = reserve_transfer_bed(db, transfer)
    sync_hospital_bed_counts(db, origin.id)
    add_transfer_event(
        db,
        transfer,
        user,
        "transfer_accepted",
        "Receiving hospital accepted the transfer request.",
        {
            "assigned_bed_id": reserved_bed.id,
            "assigned_bed_no": reserved_bed.bed_no,
            "destination_available_beds": available_beds(destination),
        },
    )
    add_transfer_event(
        db,
        transfer,
        user,
        "bed_update",
        "Receiving ICU bed reserved and origin bed released.",
        {
            "origin_hospital_id": origin.id,
            "origin_available_beds": available_beds(origin),
            "destination_hospital_id": destination.id,
            "destination_available_beds": available_beds(destination),
            "assigned_bed_id": reserved_bed.id,
        },
    )
    audit(
        db,
        user,
        "transfer_accepted",
        "transfer",
        transfer.id,
        {"assigned_bed_id": reserved_bed.id},
    )
    db.commit()
    db.refresh(transfer)

    # OSM route scoring can be expensive, so claim the ambulance in a separate,
    # short transaction after the bed reservation is safely committed.
    dispatch = DispatchService().auto_assign(db, transfer)
    if dispatch:
        add_transfer_event(
            db,
            transfer,
            user,
            "ambulance_assigned",
            f"Ambulance {dispatch.ambulance.id} assigned automatically.",
            {
                "ambulance_id": dispatch.ambulance.id,
                "distance_to_pickup_km": round(dispatch.distance_to_pickup_km, 3),
                "estimated_pickup_minutes": round(dispatch.estimated_pickup_minutes, 1),
                "pickup_risk_score": round(dispatch.pickup_risk_score, 3),
                "coverage_penalty": round(dispatch.coverage_penalty, 3),
                "dispatch_score": round(dispatch.score, 4),
                "dispatch_model": "coverage_risk_eta_dispatch_v2",
                "dispatch_reasons": dispatch.explanation,
                "score_components": dispatch.score_components,
            },
        )
    else:
        add_transfer_event(
            db,
            transfer,
            user,
            "ambulance_waiting",
            "Transfer accepted but no ambulance is currently available.",
        )
    audit(
        db,
        user,
        "transfer_accepted_auto_dispatch",
        "transfer",
        transfer.id,
        {
            "ambulance_id": dispatch.ambulance.id if dispatch else None,
            "origin_occupied_beds": origin.occupied_beds,
            "destination_occupied_beds": destination.occupied_beds,
            "assigned_bed_id": reserved_bed.id,
            "dispatch_score": round(dispatch.score, 4) if dispatch else None,
            "dispatch_reasons": dispatch.explanation if dispatch else [],
        },
    )
    db.commit()
    db.refresh(transfer)
    return transfer_to_summary(transfer)


@router.post("/transfers/{transfer_id}/reject", response_model=TransferSummary)
def reject_transfer(
    transfer_id: str,
    request: TransferActionRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> TransferSummary:
    user, _ = authenticate_access_token(db, authorization)
    transfer = db.get(TransferRequestModel, transfer_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    require_hospital_scope(user, transfer.destination_hospital_id)
    if transfer.status != TRANSFER_PENDING_DESTINATION:
        raise HTTPException(status_code=409, detail=f"Only pending requests can be rejected; current status is {transfer.status}")
    transition_transfer_atomic(db, transfer, TRANSFER_REJECTED)
    transfer.notes = request.notes or transfer.notes
    transfer.updated_at = utcnow()
    audit(db, user, "transfer_rejected", "transfer", transfer.id)
    add_transfer_event(
        db,
        transfer,
        user,
        "transfer_rejected",
        "Receiving hospital rejected the transfer request.",
        {"notes": transfer.notes},
    )
    db.commit()
    db.refresh(transfer)
    return transfer_to_summary(transfer)


@router.post("/transfers/{transfer_id}/assign-ambulance", response_model=TransferSummary)
def assign_ambulance(
    transfer_id: str,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> TransferSummary:
    user, _ = authenticate_access_token(db, authorization)
    require_super_admin(user)
    transfer = db.get(TransferRequestModel, transfer_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    dispatch = DispatchService().auto_assign(db, transfer)
    if not dispatch:
        raise HTTPException(status_code=409, detail="No available ambulance")
    transfer.updated_at = utcnow()
    audit(
        db,
        user,
        "ambulance_assigned",
        "transfer",
        transfer.id,
        {
            "ambulance_id": dispatch.ambulance.id,
            "dispatch_score": round(dispatch.score, 4),
            "dispatch_reasons": dispatch.explanation,
            "score_components": dispatch.score_components,
        },
    )
    add_transfer_event(
        db,
        transfer,
        user,
        "ambulance_assigned",
        f"Ambulance {dispatch.ambulance.id} assigned by super admin.",
        {
            "ambulance_id": dispatch.ambulance.id,
            "estimated_pickup_minutes": round(dispatch.estimated_pickup_minutes, 1),
            "pickup_risk_score": round(dispatch.pickup_risk_score, 3),
            "coverage_penalty": round(dispatch.coverage_penalty, 3),
            "dispatch_score": round(dispatch.score, 4),
            "dispatch_model": "coverage_risk_eta_dispatch_v2",
            "dispatch_reasons": dispatch.explanation,
            "score_components": dispatch.score_components,
        },
    )
    db.commit()
    db.refresh(transfer)
    return transfer_to_summary(transfer)
