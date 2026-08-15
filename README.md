# ICU Capacity-Aware Emergency Transfer DSS

Decision-support system for inter-hospital emergency ICU transfers in Colombo.

## Start the application

Backend (from the `backend/` folder, with the virtual environment active):

```bash
source .venv/bin/activate
export DEV_SEED_PASSWORD="your-local-dev-password"
python scripts/migrate.py bootstrap
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Frontend (from the `frontend/` folder, in a separate terminal):

```bash
npm install
npm run dev
```

Then open:

```text
http://127.0.0.1:5173
```

Do not start only the frontend with `npm run dev`; hospital dropdowns,
recommendations, beds, ambulances, and dashboards all require the backend on
port `8001`.

## Security baseline

Protected endpoints use real username/password authentication. Passwords are
hashed with Argon2, access tokens are short-lived signed JWTs, and refresh
sessions are rotated and revocable in the database. The browser keeps access
tokens in memory and receives refresh tokens only through an HttpOnly cookie.

The old `X-User-Id` development identity header is no longer accepted. Hospital
and ambulance scope is resolved from the authenticated database user. Live SSE
notifications use short-lived, one-use tickets instead of a user ID in the URL.

Set a local password interactively with:

```bash
python backend/scripts/set_user_password.py super-admin
```

Production startup also rejects SQLite. Use PostgreSQL/PostGIS through
`DATABASE_URL` before any real deployment.

The development database path is anchored to `backend/hospital_dss_dev.db`,
so launching Python from a different directory cannot silently select another
SQLite file. Production mode disables automatic table creation and development
seed data; reviewed migrations and administrative provisioning are required.

This project is not yet regulatory-compliant clinical software. Before live
hospital use, integrate the authentication foundation with the approved health
identity provider and MFA, perform an independent security review, and complete
clinical validation.
Bed reservation and ambulance assignment now use atomic conditional claims,
but still require PostgreSQL load testing before live deployment.

Alembic now owns the production schema. Migration and PostgreSQL commands are
documented in [the deployment guide](docs/deployment_guide.md). Existing local
SQLite data can be adopted with the guarded `bootstrap` migration command.

## Routing modes

The default application uses the local Colombo OSM driving graph in
`data/osm/colombo_drive.graphml`. The ML congestion prediction adjusts graph
travel costs, NetworkX calculates the ordered OSM node path, and the API returns
both `route_nodes` and the map-ready `polyline`.

Automatic ambulance dispatch uses the same graph. Available units are
shortlisted by proximity, then ranked by predicted pickup travel time, OSM road
risk, congestion, and their base-hospital preference. Each assigned mission
stores two independent navigation legs:

- `pickup_route`: current ambulance position to the sending hospital.
- `destination_route`: sending hospital to the receiving hospital.

Both legs contain the routing source, strategy, distance, ETA, risk score,
ordered OSM node IDs, and road-following polyline. The crew interface switches
to the destination leg when the patient is marked onboard. Legacy straight-line
mission routes remain available automatically when OSM routing is disabled or
unavailable.

After delivery, the transfer is completed and the ambulance immediately becomes
`available`, so it can be assigned to another transfer right away. If no new
assignment is made, the fleet simulator calculates a local OSM route from the
receiving hospital back to that ambulance's configured base hospital and moves
it home while keeping it available. On arrival it is parked at the base
coordinates; available ambulances no longer wander randomly around the map.

Set `OSM_GRAPH_ROUTING=0` before starting the backend to disable local graph
routing and fall back to the legacy Google/ML behavior; leave it unset (or
`1`) for normal startup, which uses OSM routing when the graph is available
and falls back automatically on errors.

You can also set `OSM_GRAPH_ROUTING=0` before startup to disable graph routing.
Regenerate the graph with:

```bash
python backend/scripts/build_osm_graph.py
```

The development backend enables a shared live fleet simulation by default.
Each hospital has two ambulances. Moving units follow cached OSRM road geometry
and update every two seconds; if routing is unavailable before a cache exists,
they remain parked instead of moving off-road. Set `FLEET_SIMULATION=0` before
starting the backend when connecting real ambulance GPS feeds.

The project combines:

- ICU bed and hospital capability management
- Patient urgency classification
- Colombo road-network modeling
- Multi-objective ambulance route optimization
- A web interface for transfer planning and route visualization

## Recommended Stack

- Frontend: React, TypeScript, Vite, Leaflet / MapLibre
- Backend API: FastAPI, Python
- Database: PostgreSQL with PostGIS
- Cache / realtime state: Redis
- ML: scikit-learn baseline, XGBoost / LightGBM if the dataset grows
- Routing: OSMnx, NetworkX, pgRouting or OSRM integration
- Deployment: Docker Compose for local, later cloud VM or Kubernetes

## Repository Layout

```text
backend/        FastAPI backend, APIs, services, data models
frontend/       React frontend, map UI, dashboards
ml/             Synthetic data generation, model training, evaluation
docs/           Architecture, API contract, database design (see docs/README.md for an index)
data/           Seed/demo data
tools/          Scripts used to generate the thesis document
```

## First Milestone

Build a working MVP that lets a user:

1. Select an origin hospital.
2. Enter patient condition and required ICU type.
3. Query hospitals with available matching ICU capacity.
4. Rank destination hospitals.
5. Show an optimized ambulance route on a map.

See [docs/project_blueprint.md](docs/project_blueprint.md) for the full plan.

For the upgraded Google traffic + OSM route-risk design, see
[docs/advanced_traffic_model.md](docs/advanced_traffic_model.md).

For local endpoint testing, see [docs/testing_guide.md](docs/testing_guide.md).

## Production-readiness documentation

- [Current architecture](docs/current_system_architecture.md)
- [Architecture audit](docs/architecture_audit.md)
- [Security threat model](docs/security_threat_model.md)
- [Deployment guide](docs/deployment_guide.md)
- [Model documentation](docs/model_documentation.md)
