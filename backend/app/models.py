from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.time_utils import utcnow


class HospitalModel(Base):
    __tablename__ = "hospitals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    icu_type: Mapped[str] = mapped_column(String, nullable=False)
    total_beds: Mapped[int] = mapped_column(Integer, nullable=False)
    occupied_beds: Mapped[int] = mapped_column(Integer, nullable=False)
    supports_trauma: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_cardiac: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_neuro: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_pediatric: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_maternity: Mapped[bool] = mapped_column(Boolean, default=False)
    has_ventilator_support: Mapped[bool] = mapped_column(Boolean, default=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    users: Mapped[list["UserModel"]] = relationship(back_populates="hospital")
    icu_beds: Mapped[list["ICUBedModel"]] = relationship(back_populates="hospital")


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_hospital_id", "hospital_id"),
        Index("ix_users_ambulance_id", "ambulance_id"),
        Index("ix_users_username", "username", unique=True),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    hospital_id: Mapped[str | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)
    ambulance_id: Mapped[str | None] = mapped_column(ForeignKey("ambulances.id"), nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    hospital: Mapped[HospitalModel | None] = relationship(back_populates="users")


class AuthSessionModel(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_id", "user_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String, nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)


class EventStreamTicketModel(Base):
    __tablename__ = "event_stream_tickets"
    __table_args__ = (
        Index("ix_event_stream_tickets_user_id", "user_id"),
        Index("ix_event_stream_tickets_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AmbulanceModel(Base):
    __tablename__ = "ambulances"
    __table_args__ = (
        Index("ix_ambulances_status", "status"),
        Index("ix_ambulances_base_status", "base_hospital_id", "status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    call_sign: Mapped[str] = mapped_column(String, nullable=False)
    base_hospital_id: Mapped[str | None] = mapped_column(ForeignKey("hospitals.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="available")
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    crew_contact: Mapped[str | None] = mapped_column(String, nullable=True)
    heading_degrees: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    speed_kph: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    route_progress_m: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    navigation_leg: Mapped[str | None] = mapped_column(String, nullable=True)
    telemetry_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ICUBedModel(Base):
    __tablename__ = "icu_beds"
    __table_args__ = (
        UniqueConstraint("hospital_id", "bed_no", name="uq_icu_beds_hospital_bed_no"),
        Index("ix_icu_beds_hospital_status", "hospital_id", "status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), nullable=False)
    bed_no: Mapped[str] = mapped_column(String, nullable=False)
    icu_type: Mapped[str] = mapped_column(String, nullable=False)
    ward: Mapped[str] = mapped_column(String, default="Ward A")
    status: Mapped[str] = mapped_column(String, default="available")
    fhir_location_id: Mapped[str | None] = mapped_column(String, nullable=True)
    operational_status: Mapped[str | None] = mapped_column(String, nullable=True)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    hospital: Mapped[HospitalModel] = relationship(back_populates="icu_beds")
    patient: Mapped["PatientRecordModel | None"] = relationship(back_populates="bed", uselist=False)


class PatientRecordModel(Base):
    __tablename__ = "patient_records"
    __table_args__ = (
        UniqueConstraint("bed_id", name="uq_patient_records_bed_id"),
        Index("ix_patient_records_hospital_id", "hospital_id"),
        Index("ix_patient_records_transfer_id", "transfer_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), nullable=False)
    bed_id: Mapped[str] = mapped_column(ForeignKey("icu_beds.id"), nullable=False)
    patient_no: Mapped[str] = mapped_column(String, nullable=False)
    patient_name: Mapped[str] = mapped_column(String, nullable=False)
    identifier_system: Mapped[str | None] = mapped_column(String, nullable=True)
    identifier_value: Mapped[str | None] = mapped_column(String, nullable=True)
    date_of_birth: Mapped[str | None] = mapped_column(String, nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str | None] = mapped_column(String, nullable=True)
    blood_type: Mapped[str | None] = mapped_column(String, nullable=True)
    condition: Mapped[str] = mapped_column(String, nullable=False)
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    vitals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    medications_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    infection_risk: Mapped[str | None] = mapped_column(String, nullable=True)
    isolation_required: Mapped[bool] = mapped_column(Boolean, default=False)
    emergency_contact: Mapped[str | None] = mapped_column(String, nullable=True)
    next_of_kin: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    transfer_id: Mapped[str | None] = mapped_column(ForeignKey("transfer_requests.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    admitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    bed: Mapped[ICUBedModel] = relationship(back_populates="patient")


class TransferRequestModel(Base):
    __tablename__ = "transfer_requests"
    __table_args__ = (
        Index("ix_transfer_requests_status", "status"),
        Index("ix_transfer_requests_origin_status", "origin_hospital_id", "status"),
        Index("ix_transfer_requests_destination_status", "destination_hospital_id", "status"),
        Index("ix_transfer_requests_ambulance_status", "ambulance_id", "status"),
        Index("ix_transfer_requests_requested_by", "requested_by_user_id"),
        Index("ix_transfer_requests_assigned_bed", "assigned_bed_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    origin_hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), nullable=False)
    destination_hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), nullable=False)
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending_acceptance")
    patient_name: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    patient_sex: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_blood_type: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_emergency_contact: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_identifier_value: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_date_of_birth: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_vitals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_medications_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_infection_risk: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_isolation_required: Mapped[bool] = mapped_column(Boolean, default=False)
    handover_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_condition: Mapped[str] = mapped_column(String, nullable=False)
    required_icu_type: Mapped[str] = mapped_column(String, nullable=False)
    urgency_class: Mapped[str] = mapped_column(String, nullable=False)
    urgency_score: Mapped[float] = mapped_column(Float, nullable=False)
    ventilator_required: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ambulance_id: Mapped[str | None] = mapped_column(ForeignKey("ambulances.id"), nullable=True)
    assigned_bed_id: Mapped[str | None] = mapped_column(ForeignKey("icu_beds.id"), nullable=True)
    route_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    pickup_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    pickup_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    dropoff_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    dropoff_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TransferEventModel(Base):
    __tablename__ = "transfer_events"
    __table_args__ = (
        Index("ix_transfer_events_transfer_created", "transfer_id", "created_at"),
        Index("ix_transfer_events_actor_user", "actor_user_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    transfer_id: Mapped[str] = mapped_column(ForeignKey("transfer_requests.id"), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BedLifecycleEventModel(Base):
    __tablename__ = "bed_lifecycle_events"
    __table_args__ = (
        Index("ix_bed_lifecycle_bed_created", "bed_id", "created_at"),
        Index("ix_bed_lifecycle_hospital_created", "hospital_id", "created_at"),
        Index("ix_bed_lifecycle_actor_user", "actor_user_id"),
        Index("ix_bed_lifecycle_patient", "patient_id"),
        Index("ix_bed_lifecycle_transfer", "transfer_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    bed_id: Mapped[str] = mapped_column(ForeignKey("icu_beds.id"), nullable=False)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    previous_status: Mapped[str | None] = mapped_column(String, nullable=True)
    new_status: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patient_records.id"), nullable=True)
    transfer_id: Mapped[str | None] = mapped_column(ForeignKey("transfer_requests.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    actor_user_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
