# Documentation Index

A guide to what's in this folder and when to read each document.

## Start here

- **[PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md)** — the original project goal, scope, and plan. Read this first for context on why the system is shaped the way it is.
- **[CURRENT_SYSTEM_ARCHITECTURE.md](CURRENT_SYSTEM_ARCHITECTURE.md)** — how the system actually works today: backend/frontend structure, routing, dispatch, data flow.

## Building and running

- **[TESTING_GUIDE.md](TESTING_GUIDE.md)** — how to start the backend/frontend locally and exercise the main endpoints.
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** — migrations, PostgreSQL/PostGIS setup, and production deployment steps.
- **[DATABASE_SCHEMA.md](DATABASE_SCHEMA.md)** — full table/column reference for the production schema.
- **[API_CONTRACT.md](API_CONTRACT.md)** — every endpoint, request/response shape, grouped by resource.

## Design and algorithms

- **[MODEL_DOCUMENTATION.md](MODEL_DOCUMENTATION.md)** — urgency scoring, dispatch ranking, capacity forecasting, and the ML training pipelines.
- **[ADVANCED_TRAFFIC_MODEL.md](ADVANCED_TRAFFIC_MODEL.md)** — the traffic/route-risk model design and how it combines with OSM graph routing.

## Review and evaluation

- **[ARCHITECTURE_AUDIT.md](ARCHITECTURE_AUDIT.md)** — a critical review of the current architecture: strengths, gaps, and technical debt.
- **[SECURITY_THREAT_MODEL.md](SECURITY_THREAT_MODEL.md)** — authentication, authorization, and data-protection posture, plus what's still needed before real clinical use.
- **[PRODUCTION_OPTIMIZATION_PLAN.md](PRODUCTION_OPTIMIZATION_PLAN.md)** — what would need to change to run this at production scale (performance, routing engine, caching).
- **[OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md)** — day-2 operations: monitoring, incident response, common failure modes.

## Suggested reading order for an examiner

1. `PROJECT_BLUEPRINT.md` — what this is and why
2. `CURRENT_SYSTEM_ARCHITECTURE.md` — how it's built
3. `MODEL_DOCUMENTATION.md` — the algorithms behind the recommendations
4. `API_CONTRACT.md` + `DATABASE_SCHEMA.md` — as reference while reading code
5. `ARCHITECTURE_AUDIT.md` + `SECURITY_THREAT_MODEL.md` — limitations and future work
