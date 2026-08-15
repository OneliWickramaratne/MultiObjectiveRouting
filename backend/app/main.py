from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from threading import Thread

from app.api.routes import admin, ambulance, auth, hospitals, predictions, routes, traffic, transfers
from app.config import settings, validate_runtime_settings
from app.seed_db import init_db
from app.services.fleet_simulation_service import fleet_simulation_service
from app.services.migration_service import assert_database_current, database_is_ready


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_runtime_settings()
    assert_database_current()
    init_db()
    Thread(target=warmup_models, daemon=True).start()
    fleet_simulation_service.start()
    yield


app = FastAPI(
    title="ICU Transfer Decision Support API",
    version="0.1.0",
    description="Capacity-aware emergency transfer recommendations for Colombo hospitals.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(hospitals.router, prefix="/api/hospitals", tags=["hospitals"])
app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(ambulance.router, prefix="/api/ambulance", tags=["ambulance"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["predictions"])
app.include_router(routes.router, prefix="/api/routes", tags=["routes"])
app.include_router(traffic.router, prefix="/api/traffic", tags=["traffic"])
app.include_router(transfers.router, prefix="/api/transfers", tags=["transfers"])


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def readiness_check() -> dict[str, str]:
    if not database_is_ready(require_current_revision=True):
        raise HTTPException(status_code=503, detail="Database is unavailable or migrations are not current")
    return {"status": "ready"}


def warmup_models() -> None:
    # Pay model/feature loading cost during startup, not on the first user click.
    for routing_service in (routes.service, transfers.service.routing_service):
        traffic_model = routing_service.traffic_model
        _ = traffic_model.feature_lookup
        _ = traffic_model.congestion_model
        _ = traffic_model.duration_model
        routing_service.osm_graph.warmup()


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")
