from pydantic import BaseModel, Field


class PatientCondition(BaseModel):
    condition_type: str = Field(examples=["respiratory", "cardiac", "trauma"])
    oxygen_saturation_band: str = Field(default="normal", examples=["normal", "low", "critical"])
    blood_pressure_band: str = Field(default="stable", examples=["stable", "unstable", "shock"])
    consciousness_level: str = Field(default="alert", examples=["alert", "reduced", "unconscious"])
    ventilator_required: bool = False


class UrgencyPredictionRequest(PatientCondition):
    required_icu_type: str = Field(examples=["medical", "surgical", "cardiac"])


class UrgencyPredictionResponse(BaseModel):
    urgency_class: str
    urgency_score: float
    explanation: list[str]


class TransferRecommendationRequest(BaseModel):
    origin_hospital_id: str = Field(examples=["nhsl"])
    required_icu_type: str = Field(examples=["medical"])
    patient_condition: PatientCondition


class HospitalSummary(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    icu_types: list[str]
    total_beds: int
    occupied_beds: int
    available_beds: int
    supports_trauma: bool = False
    supports_cardiac: bool = False
    supports_neuro: bool = False
    supports_pediatric: bool = False
    supports_maternity: bool = False
    has_ventilator_support: bool = True


class RouteRequest(BaseModel):
    origin_hospital_id: str = Field(examples=["nhsl"])
    destination_hospital_id: str = Field(examples=["lrh"])
    urgency_class: str = Field(default="high", examples=["critical", "high", "moderate"])


class RouteOption(BaseModel):
    strategy: str
    estimated_minutes: float
    distance_km: float
    risk_score: float
    total_cost: float
    congestion_ratio: float | None = None
    model_used: str | None = None
    route_source: str | None = None
    route_nodes: list[str] = Field(default_factory=list)
    route_steps: list[dict] = Field(default_factory=list)
    risk_features: dict = Field(default_factory=dict)
    risk_factors: list[str] = Field(default_factory=list)
    explanation: list[str] = Field(default_factory=list)
    polyline: list[list[float]]


class RouteOptimizationResponse(BaseModel):
    routes: list[RouteOption]


class TrafficModelStatus(BaseModel):
    google_api_enabled: bool
    congestion_model_available: bool
    duration_model_available: bool
    feature_data_available: bool
    feature_data_rows: int
    congestion_model_path: str | None = None
    duration_model_path: str | None = None
    feature_data_path: str | None = None


class TrafficSnapshotRequest(BaseModel):
    origin_hospital_ids: list[str] | None = Field(default=None, examples=[["1", "2", "6"]])
    destination_hospital_ids: list[str] | None = Field(default=None, examples=[["4", "7", "9"]])
    departure_time_iso: str | None = Field(default=None, examples=["2026-06-04T10:30:00Z"])


class TrafficSnapshotResponse(BaseModel):
    collected_rows: int
    output_path: str
    google_api_enabled: bool
    message: str


class HospitalUpdateRequest(BaseModel):
    name: str | None = None
    phone: str | None = None
    address: str | None = None
    total_beds: int | None = Field(default=None, ge=0)
    occupied_beds: int | None = Field(default=None, ge=0)
    supports_trauma: bool | None = None
    supports_cardiac: bool | None = None
    supports_neuro: bool | None = None
    supports_pediatric: bool | None = None
    supports_maternity: bool | None = None
    has_ventilator_support: bool | None = None


class PatientRecordSummary(BaseModel):
    id: str
    patient_no: str
    patient_name: str
    identifier_system: str | None = None
    identifier_value: str | None = None
    date_of_birth: str | None = None
    age: int | None = None
    sex: str | None = None
    blood_type: str | None = None
    condition: str
    diagnosis: str | None = None
    vitals: dict | None = None
    medications: list[str] = Field(default_factory=list)
    allergies: str | None = None
    infection_risk: str | None = None
    isolation_required: bool = False
    emergency_contact: str | None = None
    next_of_kin: str | None = None
    address: str | None = None
    transfer_id: str | None = None
    notes: str | None = None
    admitted_at: str
    updated_at: str


class ICUBedSummary(BaseModel):
    id: str
    hospital_id: str
    bed_no: str
    icu_type: str
    ward: str
    status: str
    fhir_location_id: str | None = None
    operational_status: str | None = None
    status_reason: str | None = None
    patient: PatientRecordSummary | None = None
    updated_at: str


class ICUBedUpdateRequest(BaseModel):
    status: str | None = Field(default=None, examples=["available", "occupied", "reserved", "cleaning", "maintenance"])
    patient_no: str | None = None
    patient_name: str | None = None
    patient_identifier_value: str | None = None
    patient_date_of_birth: str | None = None
    patient_age: int | None = Field(default=None, ge=0, le=130)
    patient_sex: str | None = None
    patient_blood_type: str | None = None
    patient_condition: str | None = None
    diagnosis: str | None = None
    vitals: dict | None = None
    medications: list[str] | None = None
    allergies: str | None = None
    infection_risk: str | None = None
    isolation_required: bool | None = None
    emergency_contact: str | None = None
    next_of_kin: str | None = None
    address: str | None = None
    notes: str | None = None
    status_reason: str | None = None
    clear_patient: bool = False


class AmbulanceSummary(BaseModel):
    id: str
    call_sign: str
    base_hospital_id: str | None
    status: str
    latitude: float
    longitude: float
    crew_contact: str | None = None
    heading_degrees: float = 0.0
    speed_kph: float = 0.0
    route_progress_m: float = 0.0
    navigation_leg: str | None = None
    telemetry_updated_at: str | None = None
    return_route_json: str | None = None


class AmbulanceUpdateRequest(BaseModel):
    status: str | None = Field(default=None, examples=["available", "assigned", "en_route", "offline"])
    latitude: float | None = None
    longitude: float | None = None
    crew_contact: str | None = None
    heading_degrees: float | None = Field(default=None, ge=0, lt=360)
    speed_kph: float | None = Field(default=None, ge=0, le=180)


class TransferCreateRequest(BaseModel):
    origin_hospital_id: str = Field(examples=["1"])
    destination_hospital_id: str = Field(examples=["9"])
    required_icu_type: str = Field(examples=["General ICU"])
    patient_condition: PatientCondition
    patient_name: str = Field(examples=["Nimal Perera"])
    patient_identifier_value: str | None = Field(default=None, examples=["NIC-198812345678"])
    patient_date_of_birth: str | None = Field(default=None, examples=["1988-04-22"])
    patient_age: int | None = Field(default=None, ge=0, le=130)
    patient_sex: str | None = Field(default=None, examples=["male", "female"])
    patient_blood_type: str | None = Field(default=None, examples=["O+"])
    patient_allergies: str | None = None
    patient_emergency_contact: str | None = None
    patient_diagnosis: str | None = None
    patient_vitals: dict | None = None
    patient_medications: list[str] | None = None
    patient_infection_risk: str | None = None
    patient_isolation_required: bool = False
    handover_notes: str | None = None
    notes: str | None = None


class TransferActionRequest(BaseModel):
    notes: str | None = None


class TransferSummary(BaseModel):
    id: str
    origin_hospital_id: str
    destination_hospital_id: str
    status: str
    patient_name: str | None = None
    patient_age: int | None = None
    patient_sex: str | None = None
    patient_blood_type: str | None = None
    patient_allergies: str | None = None
    patient_emergency_contact: str | None = None
    patient_identifier_value: str | None = None
    patient_date_of_birth: str | None = None
    patient_diagnosis: str | None = None
    patient_vitals: dict | None = None
    patient_medications: list[str] = Field(default_factory=list)
    patient_infection_risk: str | None = None
    patient_isolation_required: bool = False
    handover: dict | None = None
    patient_condition: str
    required_icu_type: str
    urgency_class: str
    urgency_score: float
    ventilator_required: bool
    ambulance_id: str | None = None
    notes: str | None = None
    route_payload_json: str | None = None
    assigned_bed_id: str | None = None
    pickup_latitude: float | None = None
    pickup_longitude: float | None = None
    dropoff_latitude: float | None = None
    dropoff_longitude: float | None = None
    created_at: str
    updated_at: str


class TransferEventSummary(BaseModel):
    id: str
    transfer_id: str
    actor_user_id: str | None = None
    event_type: str
    status: str
    message: str
    details_json: str | None = None
    created_at: str


class BedLifecycleEventSummary(BaseModel):
    id: str
    bed_id: str
    hospital_id: str
    actor_user_id: str | None = None
    previous_status: str | None = None
    new_status: str
    reason: str | None = None
    patient_id: str | None = None
    transfer_id: str | None = None
    created_at: str


class AmbulanceMissionResponse(BaseModel):
    ambulance: AmbulanceSummary
    active_transfer: TransferSummary | None
    return_route_json: str | None = None


class UserSummary(BaseModel):
    id: str
    name: str
    role: str
    hospital_id: str | None = None
    ambulance_id: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=8, max_length=256)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserSummary


class EventStreamTicketResponse(BaseModel):
    ticket: str
    expires_in: int


class DashboardSummary(BaseModel):
    hospitals: list[HospitalSummary]
    ambulances: list[AmbulanceSummary]
    transfers: list[TransferSummary]


class CapacityForecastPointSummary(BaseModel):
    horizon_hours: int
    predicted_available_beds: int
    predicted_occupied_beds: int
    pressure_score: float
    pressure_level: str


class HospitalCapacityForecastSummary(BaseModel):
    hospital_id: str
    hospital_name: str
    total_beds: int
    current_available_beds: int
    current_occupied_beds: int
    inbound_transfers: int
    expected_discharges_12h: float
    expected_cleaning_recoveries_12h: float
    points: list[CapacityForecastPointSummary]
    recommended_action: str


class CapacityForecastSummary(BaseModel):
    generated_at: str
    network_pressure_level: str
    network_pressure_score: float
    network_recommended_action: str
    hospitals: list[HospitalCapacityForecastSummary]


class SimulationScenarioRequest(BaseModel):
    scenario: str = Field(default="evening_surge", examples=["evening_surge"])
    duration_hours: int = Field(default=6, ge=1, le=24)
    intensity: float = Field(default=1.0, ge=0.25, le=3.0)


class SimulationHospitalImpactSummary(BaseModel):
    hospital_id: str
    hospital_name: str
    current_available_beds: int
    projected_arrivals: int
    projected_releases: float
    predicted_available_beds: int
    shortage_beds: int
    pressure_score: float
    pressure_level: str
    recommended_action: str


class SimulationAnalyticsSummary(BaseModel):
    generated_at: str
    scenario: str
    scenario_label: str
    description: str
    duration_hours: int
    intensity: float
    simulated_transfers: int
    critical_transfers: int
    ambulances_required: int
    available_ambulances: int
    ambulance_gap: int
    total_available_beds: int
    total_beds: int
    shortage_hospitals: int
    total_shortage_beds: int
    network_pressure_level: str
    network_pressure_score: float
    recommended_action: str
    hospital_impacts: list[SimulationHospitalImpactSummary]


class HospitalRecommendation(BaseModel):
    destination_hospital_id: str
    destination_name: str
    rank: int
    score: float
    available_beds: int
    estimated_minutes: float
    route_risk_score: float
    reasons: list[str]


class TransferRecommendationResponse(BaseModel):
    urgency_class: str
    urgency_score: float
    recommendations: list[HospitalRecommendation]
