from fastapi import APIRouter

from app.schemas import UrgencyPredictionRequest, UrgencyPredictionResponse
from app.services.urgency_service import UrgencyService

router = APIRouter()
service = UrgencyService()


@router.post("/urgency", response_model=UrgencyPredictionResponse)
def predict_urgency(request: UrgencyPredictionRequest) -> UrgencyPredictionResponse:
    return service.predict(request)
