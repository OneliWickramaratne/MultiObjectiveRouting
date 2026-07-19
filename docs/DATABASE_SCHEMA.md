# Database Schema

Database: PostgreSQL with PostGIS.

## hospitals

| Column | Type | Notes |
| --- | --- | --- |
| id | text primary key | Stable hospital identifier |
| name | text | Hospital name |
| type | text | teaching, general, specialized |
| address | text | Optional |
| latitude | numeric | WGS84 latitude |
| longitude | numeric | WGS84 longitude |
| geom | geography(Point, 4326) | PostGIS point |
| active | boolean | Soft enable/disable |

## icu_units

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid primary key | ICU unit id |
| hospital_id | text foreign key | Linked hospital |
| icu_type | text | medical, surgical, pediatric, cardiac, trauma, neuro |
| total_beds | integer | Total ICU beds |
| ventilator_supported | boolean | Whether ventilators are supported |
| supported_conditions | text[] | Matching condition categories |

## icu_bed_status

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid primary key | Status event id |
| icu_unit_id | uuid foreign key | Linked ICU unit |
| occupied_beds | integer | Current occupied beds |
| available_beds | integer | Generated or calculated |
| source | text | manual, synthetic, integration |
| updated_at | timestamptz | Status timestamp |
| updated_by | text | User/system |

## transfer_requests

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid primary key | Transfer request id |
| origin_hospital_id | text | Starting hospital |
| required_icu_type | text | Needed ICU |
| condition_type | text | Patient condition category |
| urgency_class | text | critical, high, moderate |
| urgency_score | numeric | 0 to 1 |
| created_at | timestamptz | Request time |

## route_options

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid primary key | Route option id |
| transfer_request_id | uuid foreign key | Linked request |
| destination_hospital_id | text | Candidate hospital |
| strategy | text | shortest_time, multi_objective |
| estimated_minutes | numeric | Estimated transfer time |
| distance_km | numeric | Route distance |
| risk_score | numeric | 0 to 1 |
| total_score | numeric | Recommendation score |
| geometry | geography(LineString, 4326) | Route line |

## users

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid primary key | User id |
| name | text | Display name |
| email | text unique | Login identity |
| role | text | dispatcher, hospital_admin, researcher |
| hospital_id | text nullable | Hospital scope |

## audit_logs

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid primary key | Audit event id |
| actor_user_id | uuid | User who acted |
| action | text | Event name |
| entity_type | text | Entity changed |
| entity_id | text | Entity id |
| created_at | timestamptz | Event time |

## Current Implementation

The backend now uses SQLAlchemy models in:

```text
backend/app/models.py
```

Default local development database:

```text
backend/hospital_dss_dev.db
```

Production target:

```text
PostgreSQL + PostGIS
```

Set this environment variable before starting FastAPI to use PostgreSQL:

```powershell
$env:DATABASE_URL="postgresql+psycopg://hospital_dss:hospital_dss@localhost:5432/hospital_dss"
```

Seed/init command:

```powershell
cd C:\Users\antho\OneDrive\Documents\Hospital\backend
& C:\Users\antho\AppData\Local\Programs\Python\Python313\python.exe -m app.seed_db
```

## Operational Workflow Tables

The current database-backed MVP includes:

- `hospitals`: hospital profile, ICU capability, current occupied beds
- `users`: super admin and one admin user per hospital
- `ambulances`: ambulance pool, status, current/base location
- `transfer_requests`: hospital A to hospital B transfer request lifecycle
- `audit_logs`: update/action trail

Transfer status flow:

```text
pending_acceptance
accepted_pending_ambulance
ambulance_assigned
en_route_pickup
en_route_dropoff
completed
```

Rejection status:

```text
rejected
```

Ambulance dispatch is automated after the destination hospital accepts the transfer. The dispatcher currently selects the available ambulance with the best score:

```text
score = distance_to_pickup_km - same_origin_hospital_bonus
```

The selected ambulance receives a mission through:

```text
GET /api/ambulance/mission
```

Mission actions:

```text
start-pickup
arrive-pickup
complete
```
