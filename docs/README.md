# Documentation Index

A guide to what's in this folder and when to read each document.

## Start here

- **[project_blueprint.md](project_blueprint.md)** — the original project goal, scope, and plan. Read this first for context on why the system is shaped the way it is.
- **[current_system_architecture.md](current_system_architecture.md)** — how the system actually works today: backend/frontend structure, routing, dispatch, data flow.

## Building and running

- **[testing_guide.md](testing_guide.md)** — how to start the backend/frontend locally and exercise the main endpoints.
- **[deployment_guide.md](deployment_guide.md)** — migrations, PostgreSQL/PostGIS setup, and production deployment steps.
- **[database_schema.md](database_schema.md)** — full table/column reference for the production schema.
- **[api_contract.md](api_contract.md)** — every endpoint, request/response shape, grouped by resource.

## Design and algorithms

- **[model_documentation.md](model_documentation.md)** — urgency scoring, dispatch ranking, capacity forecasting, and the ML training pipelines.
- **[advanced_traffic_model.md](advanced_traffic_model.md)** — the traffic/route-risk model design and how it combines with OSM graph routing.

## Review and evaluation

- **[evaluation_results.md](evaluation_results.md)** — measured results: urgency model comparison, routing risk/time tradeoff, traffic model comparison.
- **[architecture_audit.md](architecture_audit.md)** — a critical review of the current architecture: strengths, gaps, and technical debt.
- **[security_threat_model.md](security_threat_model.md)** — authentication, authorization, and data-protection posture, plus what's still needed before real clinical use.
- **[production_optimization_plan.md](production_optimization_plan.md)** — what would need to change to run this at production scale (performance, routing engine, caching).
- **[operations_runbook.md](operations_runbook.md)** — day-2 operations: monitoring, incident response, common failure modes.

## Suggested reading order for an examiner

1. `project_blueprint.md` — what this is and why
2. `current_system_architecture.md` — how it's built
3. `model_documentation.md` — the algorithms behind the recommendations
4. `evaluation_results.md` — measured results validating the design
5. `api_contract.md` + `database_schema.md` — as reference while reading code
6. `architecture_audit.md` + `security_threat_model.md` — limitations and future work
