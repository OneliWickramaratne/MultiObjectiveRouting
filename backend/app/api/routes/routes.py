from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import RouteOptimizationResponse, RouteRequest
from app.services.db_adapters import hospital_from_model, resolve_hospital_model
from app.services.routing_service import RoutingService

router = APIRouter()
service = RoutingService()


@router.post("/optimize", response_model=RouteOptimizationResponse)
def optimize_route(request: RouteRequest, db: Session = Depends(get_db)) -> RouteOptimizationResponse:
    origin_row = resolve_hospital_model(db, request.origin_hospital_id)
    destination_row = resolve_hospital_model(db, request.destination_hospital_id)
    origin = hospital_from_model(db, origin_row) if origin_row else None
    destination = hospital_from_model(db, destination_row) if destination_row else None
    if not origin or not destination:
        raise HTTPException(status_code=404, detail="Origin or destination hospital not found")
    return RouteOptimizationResponse(
        routes=service.compare_routes(origin, destination, request.urgency_class)
    )
