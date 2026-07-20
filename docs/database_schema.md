# Database Schema

This documents the **actual current schema** as implemented in
`backend/app/models.py` (SQLAlchemy). This replaces an earlier draft that
described a different, PostGIS-native design used for initial planning —
that design was reworked during implementation to the schema below.

Local development runs on **SQLite** (`backend/hospital_dss_dev.db`).
Production is designed to run on **PostgreSQL** using the same schema
(SQLAlchemy is database-agnostic; no PostGIS-specific column types are
required by the current design, since geographic queries are handled at
the application layer using latitude/longitude columns rather than a
native `geography` type).

## hospitals

| Column | Type | Notes |
|---|---|---|
| id | text primary key | Stable hospital identifier |
| name | text | Hospital name |
| latitude / longitude | float | WGS84 coordinates |
| icu_type | text | Primary/display ICU type label |
| total_beds / occupied_beds | integer | Kept in sync from `icu_beds` |
| supports_trauma / cardiac / neuro / pediatric / maternity | boolean | Condition-support flags |
| has_ventilator_support | boolean | |
| phone / address | text, nullable | |
| updated_at | datetime | |

Note: a hospital's real ICU **specialty mix** is derived from its
`icu_beds` rows (a hospital can run more than one ICU type at once —
see below), not from the single `icu_type` column, which is only a
display label.

## icu_beds

Bed-level records — this is the actual source of truth for capacity and
specialty, not a hospital-level aggregate.

| Column | Type | Notes |
|---|---|---|
| id | text primary key | |
| hospital_id | FK → hospitals.id | |
| bed_no | text | Unique per hospital |
| icu_type | text | This specific bed's ICU specialty |
| ward | text | Ward/room grouping |
| status | text | available, occupied, reserved, transfer_assigned, cleaning, maintenance |
| fhir_location_id | text, nullable | For future HL7 FHIR integration |
| operational_status / status_reason | text, nullable | |
| updated_at | datetime | |

Relationship: one bed → at most one `patient_records` row.

## patient_records

Patient identity and clinical packet, linked 1:1 to an occupied bed and
optionally to the transfer that brought them there.

## users

| Column | Type | Notes |
|---|---|---|
| id | text primary key | |
| name | text | |
| role | text | super_admin, hospital_admin, ambulance_crew |
| hospital_id | FK, nullable | Scope for hospital admins |
| ambulance_id | FK, nullable | Scope for ambulance crew |
| username | text, unique | Login identity (not email) |
| password_hash | text, nullable | Argon2 hash |
| is_active | boolean | |
| failed_login_count / locked_until | | Brute-force lockout |
| last_login_at / password_changed_at | datetime, nullable | |

## auth_sessions / event_stream_tickets

Support refresh-token session tracking and short-lived tickets for
authenticating the ambulance telemetry WebSocket connection.

## ambulances

| Column | Type | Notes |
|---|---|---|
| id | text primary key | |
| call_sign | text | |
| base_hospital_id | FK, nullable | |
| status | text | available, assigned, en_route, transporting, offline |
| latitude / longitude | float | Live position |
| crew_contact | text, nullable | |
| heading_degrees / speed_kph / route_progress_m | float | Motion telemetry |
| navigation_leg | text, nullable | |
| telemetry_updated_at | datetime, nullable | |

## transfer_requests

The central workflow table — one row per transfer, carrying both the
operational state and the full clinical handover packet.

| Column | Type | Notes |
|---|---|---|
| id | text primary key | |
| origin_hospital_id / destination_hospital_id | FK | |
| requested_by_user_id | FK → users.id | |
| status | text | pending_acceptance → accepted_pending_ambulance → ambulance_assigned → ambulance_en_route_to_pickup → en_route_to_destination → completed (or rejected) |
| patient_name, age, sex, blood_type, allergies, emergency_contact, identifier_value, date_of_birth, diagnosis | | Patient identity/clinical fields |
| patient_vitals_json / patient_medications_json / handover_json | text | JSON-encoded structured fields |
| patient_condition / required_icu_type | text | Drives hospital matching |
| urgency_class / urgency_score | text / float | From the urgency scoring service |
| ventilator_required | boolean | |
| ambulance_id | FK, nullable | Set once dispatched |
| assigned_bed_id | FK → icu_beds.id, nullable | Reserved on acceptance |
| route_payload_json | text | JSON: `{pickup_route, destination_route, mission_route, dispatch}` |
| pickup/dropoff latitude/longitude | float, nullable | |
| created_at / updated_at | datetime | |

## transfer_events / bed_lifecycle_events / audit_logs

Append-only event tables recording, respectively: transfer status
changes with actor and message, ICU bed status transitions with reason,
and general admin actions — the audit trail behind every workflow step.

## Full authoritative reference

For exact column types, constraints, and indexes, the definitive source
is `backend/app/models.py` — this document is a human-readable summary
of it, not a replacement for it.
