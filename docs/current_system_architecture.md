# Current System Architecture

Last reviewed: 2026-07-23

## Purpose

This repository implements a Colombo ICU transfer decision-support system. It supports hospital operators, receiving hospital admins, ambulance crews, and a super-admin view for capacity, routing, transfer coordination, ambulance assignment, and simulation.

The system is decision support only. Recommendations must remain explainable and must not replace clinician or dispatcher confirmation.

## Repository Structure

- `backend/app/main.py` starts FastAPI, mounts routers, initializes the development database, warms routing and model services, and starts the fleet simulation thread.
- `backend/app/models.py` defines SQLAlchemy models for hospitals, users, ambulances, ICU beds, patient records, transfers, transfer events, bed lifecycle events, and audit logs.
- `backend/app/schemas.py` defines Pydantic request and response contracts.
- `backend/app/api/routes/` contains HTTP routes for admin, ambulance, hospitals, predictions, routes, traffic, and transfer recommendations.
- `backend/app/services/` contains urgency scoring, transfer recommendation, traffic prediction, OSM routing, dispatch, capacity forecasting, simulation analytics, sensitive-data redaction, and transfer state validation.
- `backend/scripts/` contains the migration bootstrap script and the reproducible evaluation scripts (`eval_routing.py`, `eval_dispatch.py`, `eval_simulation.py`) and their chart generators, each calling the production service classes directly rather than a separate simulation.
- `frontend/src/pages/` contains one file per screen (Overview, Transfer planner, Requests, Fleet, Capacity, ICU beds, Transfers, Alerts, Network map, Active mission).
- `frontend/src/components/ThreeDNavigationMap.tsx` provides MapLibre-based driver navigation.
- `ml/` contains the synthetic urgency dataset and the training scripts for both the urgency baseline (`train_urgency_model.py`) and the traffic congestion/duration models (`train_traffic_models.py`). The `.joblib` artifacts they produce are gitignored rather than committed, so a fresh clone regenerates them by running those two scripts; see the root `README.md`.
- `data/osm/colombo_drive.graphml` is the real Colombo road network graph used by OSM routing (63,951 nodes, 126,278 edges).
- `docs/` contains architecture, API, database, traffic-model, testing, deployment, security, and evaluation-results documentation; `docs/README.md` indexes them in a suggested reading order.

## Backend Entry Points

- FastAPI app: `backend/app/main.py`
- Startup: `init_db()`, model/routing warmup, `fleet_simulation_service.start()`
- Health endpoints: `GET /health`, `GET /ready`
- Local development startup: `source .venv/bin/activate && python -m uvicorn app.main:app --host 127.0.0.1 --port 8001` (see `docs/testing_guide.md`)

## API Endpoints

Public or operational endpoints:

- `GET /api/hospitals`
- `GET /api/hospitals/{hospital_id}`
- `POST /api/predictions/urgency`
- `POST /api/routes/optimize`
- `GET /api/traffic/status`
- `POST /api/traffic/collect-snapshot`
- `POST /api/transfers/recommend`

Authenticated admin/crew endpoints:

- `GET /api/admin/dashboard`
- `GET /api/admin/capacity/forecast`
- `POST /api/admin/simulation/run`
- `GET /api/admin/events/stream`
- `GET /api/admin/users`
- `GET /api/admin/transfers/{transfer_id}/events`
- `PATCH /api/admin/hospitals/{hospital_id}`
- `GET /api/admin/hospitals/{hospital_id}/icu-beds`
- `GET /api/admin/icu-beds/{bed_id}/lifecycle`
- `PATCH /api/admin/icu-beds/{bed_id}`
- `GET /api/admin/ambulances`
- `PATCH /api/admin/ambulances/{ambulance_id}`
- `POST /api/admin/transfers`
- `POST /api/admin/transfers/{transfer_id}/accept`
- `POST /api/admin/transfers/{transfer_id}/reject`
- `POST /api/admin/transfers/{transfer_id}/assign-ambulance`
- `GET /api/ambulance/mission`
- `PATCH /api/ambulance/location`
- `POST /api/ambulance/mission/{transfer_id}/{action}`

## Data Model

Primary entities:

- `HospitalModel`: hospital identity, location, a primary ICU type label, high-level bed counts. A hospital's real ICU specialty mix (a hospital can run more than one ICU ward at once, e.g. Trauma + General + Cardiac) is derived from its `ICUBedModel` rows, not this single label.
- `UserModel`: operator identity, role, Argon2 credential hash, activation, and lockout state.
- `AuthSessionModel`: revocable refresh session with hashed rotating refresh and CSRF secrets.
- `EventStreamTicketModel`: short-lived one-use authorization for browser SSE connections.
- `AmbulanceModel`: call sign, base hospital, status, last location.
- `ICUBedModel`: hospital bed, ICU type, ward, status, FHIR-like location fields.
- `PatientRecordModel`: patient details assigned to ICU beds or incoming transfers.
- `TransferRequestModel`: sending hospital, receiving hospital, patient handover details, urgency, ambulance, route, and assigned bed.
- `TransferEventModel`: operational transfer timeline.
- `BedLifecycleEventModel`: bed status audit trail.
- `AuditLogModel`: application-level action audit, with sensitive fields redacted by code.

## Authentication and Authorization

Current production-hardening state:

- Protected endpoints require a signed bearer token tied to an active database session.
- Passwords are Argon2-hashed; refresh secrets are hashed, rotated, revocable, and delivered in an HttpOnly SameSite cookie.
- Refresh and logout operations require a matching CSRF cookie/header pair.
- SSE connections require a short-lived one-use ticket issued through bearer authentication.
- `X-User-Id` is no longer an authentication mechanism.
- Production startup fails if `ALLOW_DEFAULT_DEV_USER=1`.
- Production startup fails if SQLite is used.
- Role and resource checks exist for super admin, hospital admin scope, transfer scope, and ambulance crew mission scope.

Remaining rollout gap:

- Approved identity-provider federation and MFA are still required before live hospital deployment.
- Network-level rate limiting, centralized security monitoring, and independent penetration testing remain deployment controls.

## Transfer Lifecycle

Current transfer states are guarded by `services/transfer_state_machine.py`:

1. `pending_destination_acceptance`
2. `accepted_pending_ambulance`
3. `ambulance_assigned`
4. `ambulance_en_route_to_pickup`
5. `en_route_to_destination`
6. `completed`

Terminal alternatives:

- `rejected`
- `cancelled`

Invalid direct transitions, such as pending to completed or completed to assigned, now raise `409 Conflict`.

## Bed Reservation Lifecycle

- Receiving hospital accepts transfer.
- `reserve_transfer_bed()` finds an available destination ICU bed matching the specific requested ICU type — a hospital with a full Cardiac ICU but an open Trauma ICU bed remains eligible for a trauma transfer.
- Bed becomes `transfer_assigned`.
- A patient record is created from the transfer handover.
- On ambulance completion, the bed becomes `occupied`.
- Manual bed updates can create, update, clear, or change patient assignment.
- `sync_hospital_bed_counts()` recalculates high-level hospital counts from bed rows.

Important limitation: bed selection is not yet protected by row-level locks or uniqueness constraints, so concurrent accept requests remain a production risk on SQLite and require PostgreSQL transactional locking.

## Ambulance Assignment Lifecycle

- `DispatchService.auto_assign()` filters `available` ambulances.
- It ranks nearest candidates by pickup ETA, route risk, base coverage impact, stale-location penalty, and base-hospital match.
- Selected ambulance is set to `assigned`.
- Route payload stores `pickup_route`, `destination_route`, and backward-compatible `mission_route`.
- Crew actions move the transfer through pickup, destination, and completion states.
- Completed ambulance is immediately `available`; fleet simulation returns it to base if unassigned.

Important limitation: assignment is not yet protected by row-level locks or compare-and-set updates, so concurrent dispatchers can race in production.

Measured evaluation: a dedicated comparison against a naive nearest-distance baseline found the heuristic diverges in 2 of 10 tested scenarios, trading small increases in pickup distance for meaningful reductions in pickup-route risk — see `docs/evaluation_results.md`, reproducible via `backend/scripts/eval_dispatch.py`.

## Routing Logic

- Local OSM graph routing lives in `OSMGraphRoutingService`, using NetworkX A* search with a zero heuristic (mathematically equivalent to Dijkstra) over the real Colombo road graph (63,951 nodes, 126,278 edges).
- Route source is labelled as local OSM graph or fallback route.
- The graph returns ordered node IDs, road-following polyline, route steps, risk features, risk factors, and explanations.
- `RoutingService` compares `shortest_time` and `ml_traffic_risk_aware`, weighted by urgency-specific time/risk/distance factors.
- Google Routes API support exists as an optional traffic-data collector/integration path.
- A malformed or missing graph file is caught and handled as a graceful fail-open fallback rather than crashing the caller.

Measured evaluation: the urgency-aware strategy reduces road-risk exposure by 13.3%–17.7% depending on urgency, at a time cost scaling from effectively zero (critical) to +0.125 minutes (moderate) — see `docs/evaluation_results.md`, reproducible via `backend/scripts/eval_routing.py`.

## AI and ML Logic

- Urgency is rule-based via `UrgencyService`; a Gradient Boosting classifier trained on synthetic data is evaluated against it and against Logistic Regression/Random Forest baselines (85.0% accuracy, best critical-class recall) — see `docs/evaluation_results.md`, reproducible via `ml/train_urgency_model.py` and `ml/generate_urgency_chart.py`.
- Traffic prediction uses `TrafficModelService`, cached feature rows, and joblib models when present (Random Forest for congestion ratio, R²=0.978; Gradient Boosting for duration, R²=0.991), trained on one real week of Google Routes API data extended synthetically.
- Capacity forecasting uses deterministic projected arrivals/releases.
- Simulation analytics are read-only scenario calculations, evaluated across all four built-in scenarios — see `docs/evaluation_results.md`, reproducible via `backend/scripts/eval_simulation.py`.

Model governance remains incomplete: model cards, training provenance, validation metrics, drift monitoring, and rollback registry must be added before production.

## Realtime and Background Processes

- Admin realtime updates use Server-Sent Events at `/api/admin/events/stream`.
- Fleet simulation runs in a background thread every two seconds.
- Routing/model warmup runs on startup in a background thread.

Limitations:

- SSE authentication is query-parameter based and should move to proper token auth.
- Background fleet simulation uses in-process state and should move to a managed worker or disable in production when live GPS is connected.

## Data Source Labels

- Confirmed/manual bed status: `ICUBedModel.status`.
- Forecast capacity: `CapacityForecastService`; labelled predictive.
- Scenario capacity: `SimulationAnalyticsService`; labelled read-only simulation.
- Routing source: included in route payloads.
- Traffic model source: `trained_congestion_model` or `fallback_time_formula`.

## Baseline Verification

- Backend compiles cleanly and imports without error.
- Frontend production build passes (`npm run build`).
- Five quantitative evaluation scripts run successfully end-to-end against the production service classes — see `docs/evaluation_results.md`.
- Known warning: Vite reports a large `ThreeDNavigationMap` chunk above 500 kB, since the 3D driver-navigation map is only needed in ambulance crew mode.
