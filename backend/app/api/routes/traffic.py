from fastapi import APIRouter

from app.schemas import TrafficModelStatus, TrafficSnapshotRequest, TrafficSnapshotResponse
from app.services.traffic_collection_service import TrafficCollectionService
from app.services.traffic_model_service import TrafficModelService

router = APIRouter()


@router.get("/status", response_model=TrafficModelStatus)
def get_traffic_status() -> TrafficModelStatus:
    service = TrafficModelService()
    feature_data = service.feature_data
    return TrafficModelStatus(
        google_api_enabled=service.google_routes_enabled,
        congestion_model_available=service.congestion_model is not None,
        duration_model_available=service.duration_model is not None,
        feature_data_available=feature_data is not None,
        feature_data_rows=0 if feature_data is None else len(feature_data),
        congestion_model_path=str(service.model_path) if service.model_path else None,
        duration_model_path=str(service.duration_model_path) if service.duration_model_path else None,
        feature_data_path=str(service.feature_data_path) if service.feature_data_path else None,
    )


@router.post("/collect-snapshot", response_model=TrafficSnapshotResponse)
def collect_traffic_snapshot(request: TrafficSnapshotRequest) -> TrafficSnapshotResponse:
    service = TrafficCollectionService()
    result = service.collect_snapshot(request)
    return TrafficSnapshotResponse(**result)
