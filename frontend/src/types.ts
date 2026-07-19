// Centralized domain types for the ICU Transfer DSS frontend.
// Extracted from the original monolithic App.tsx so every page/component
// can share one source of truth instead of redeclaring shapes.

export type Hospital = {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  icu_types: string[];
  total_beds: number;
  occupied_beds: number;
  available_beds: number;
  supports_trauma: boolean;
  supports_cardiac: boolean;
  supports_neuro: boolean;
  supports_pediatric: boolean;
  supports_maternity: boolean;
};

export type UserSummary = {
  id: string;
  name: string;
  role: string;
  hospital_id: string | null;
  ambulance_id: string | null;
};

export type AuthTokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserSummary;
};

export type PatientRecord = {
  id: string;
  patient_no: string;
  patient_name: string;
  identifier_system: string | null;
  identifier_value: string | null;
  date_of_birth: string | null;
  age: number | null;
  sex: string | null;
  blood_type: string | null;
  condition: string;
  diagnosis: string | null;
  vitals: Record<string, unknown> | null;
  medications: string[];
  allergies: string | null;
  infection_risk: string | null;
  isolation_required: boolean;
  emergency_contact: string | null;
  next_of_kin: string | null;
  address: string | null;
  transfer_id: string | null;
  notes: string | null;
  admitted_at: string;
  updated_at: string;
};

export type IcuBed = {
  id: string;
  hospital_id: string;
  bed_no: string;
  icu_type: string;
  ward: string;
  status: string;
  fhir_location_id: string | null;
  operational_status: string | null;
  status_reason: string | null;
  patient: PatientRecord | null;
  updated_at: string;
};

export type Recommendation = {
  destination_hospital_id: string;
  destination_name: string;
  rank: number;
  score: number;
  available_beds: number;
  estimated_minutes: number;
  route_risk_score: number;
  reasons: string[];
};

export type TransferResponse = {
  urgency_class: string;
  urgency_score: number;
  recommendations: Recommendation[];
};

export type RouteStep = {
  start_index: number;
  end_index: number;
  road_name: string;
  maneuver: "depart" | "continue" | "left" | "right" | "sharp_left" | "sharp_right" | string;
  distance_meters: number;
  estimated_seconds?: number;
  average_risk?: number | null;
  instruction?: string;
};

export type RouteOption = {
  strategy: string;
  estimated_minutes: number;
  distance_km: number;
  risk_score: number;
  total_cost: number;
  congestion_ratio: number | null;
  model_used: string | null;
  route_source: string | null;
  route_nodes: string[];
  route_steps: RouteStep[];
  risk_features: Record<string, unknown>;
  risk_factors: string[];
  explanation: string[];
  polyline: [number, number][];
};

export type RouteResponse = {
  routes: RouteOption[];
};

export type AmbulanceSummary = {
  id: string;
  call_sign: string;
  base_hospital_id: string | null;
  status: string;
  latitude: number;
  longitude: number;
  heading_degrees: number;
  speed_kph: number;
  route_progress_m: number;
  navigation_leg: string | null;
  telemetry_updated_at: string | null;
  return_route_json?: string | null;
};

export type TransferSummary = {
  id: string;
  origin_hospital_id: string;
  destination_hospital_id: string;
  status: string;
  patient_name: string | null;
  patient_age: number | null;
  patient_sex: string | null;
  patient_blood_type: string | null;
  patient_allergies: string | null;
  patient_emergency_contact: string | null;
  patient_identifier_value: string | null;
  patient_date_of_birth: string | null;
  patient_diagnosis: string | null;
  patient_vitals: Record<string, unknown> | null;
  patient_medications: string[];
  patient_infection_risk: string | null;
  patient_isolation_required: boolean;
  handover: Record<string, unknown> | null;
  patient_condition: string;
  required_icu_type: string;
  urgency_class: string;
  urgency_score: number;
  ambulance_id: string | null;
  notes: string | null;
  route_payload_json?: string | null;
  assigned_bed_id?: string | null;
  pickup_latitude?: number | null;
  pickup_longitude?: number | null;
  dropoff_latitude?: number | null;
  dropoff_longitude?: number | null;
  created_at?: string;
  updated_at?: string;
};

export type TransferEventSummary = {
  id: string;
  transfer_id: string;
  actor_user_id: string | null;
  event_type: string;
  status: string;
  message: string;
  details_json: string | null;
  created_at: string;
};

export type DispatchPayload = {
  model?: string;
  score?: number;
  estimated_pickup_minutes?: number;
  distance_to_pickup_km?: number;
  pickup_risk_score?: number;
  coverage_penalty?: number;
  explanation?: string[];
  candidate_rankings?: Array<{
    ambulance_id: string;
    call_sign: string;
    score: number;
    estimated_pickup_minutes: number;
    pickup_risk_score: number;
    coverage_penalty: number;
    reasons: string[];
  }>;
};

export type DashboardSummary = {
  hospitals: Hospital[];
  ambulances: AmbulanceSummary[];
  transfers: TransferSummary[];
};

export type CapacityForecastPoint = {
  horizon_hours: number;
  predicted_available_beds: number;
  predicted_occupied_beds: number;
  pressure_score: number;
  pressure_level: string;
};

export type HospitalCapacityForecast = {
  hospital_id: string;
  hospital_name: string;
  total_beds: number;
  current_available_beds: number;
  current_occupied_beds: number;
  inbound_transfers: number;
  expected_discharges_12h: number;
  expected_cleaning_recoveries_12h: number;
  points: CapacityForecastPoint[];
  recommended_action: string;
};

export type CapacityForecastSummary = {
  generated_at: string;
  network_pressure_level: string;
  network_pressure_score: number;
  network_recommended_action: string;
  hospitals: HospitalCapacityForecast[];
};

export type SimulationHospitalImpact = {
  hospital_id: string;
  hospital_name: string;
  current_available_beds: number;
  projected_arrivals: number;
  projected_releases: number;
  predicted_available_beds: number;
  shortage_beds: number;
  pressure_score: number;
  pressure_level: string;
  recommended_action: string;
};

export type SimulationAnalyticsSummary = {
  generated_at: string;
  scenario: string;
  scenario_label: string;
  description: string;
  duration_hours: number;
  intensity: number;
  simulated_transfers: number;
  critical_transfers: number;
  ambulances_required: number;
  available_ambulances: number;
  ambulance_gap: number;
  total_available_beds: number;
  total_beds: number;
  shortage_hospitals: number;
  total_shortage_beds: number;
  network_pressure_level: string;
  network_pressure_score: number;
  recommended_action: string;
  hospital_impacts: SimulationHospitalImpact[];
};

export type AmbulanceMission = {
  ambulance: AmbulanceSummary;
  active_transfer: TransferSummary | null;
  return_route_json?: string | null;
};

export type MissionRoutePayload = {
  source?: string;
  strategy?: string;
  distance_km?: number;
  estimated_minutes?: number;
  risk_score?: number | null;
  route_nodes?: string[];
  route_steps?: RouteStep[];
  risk_features?: Record<string, unknown>;
  risk_factors?: string[];
  explanation?: string[];
  polyline?: [number, number][];
};

export type BlockingModal = {
  title: string;
  message: string;
  tone?: "info" | "warning" | "success";
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm?: () => void | Promise<void>;
  onCancel?: () => void;
};

// Urgency / pressure levels drive the "triage spine" color coding used
// throughout the redesigned UI (see styles/tokens.css).
export type UrgencyLevel = "critical" | "high" | "moderate" | string;
export type PressureLevel = "stable" | "elevated" | "high" | "critical" | string;
