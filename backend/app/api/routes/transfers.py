from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import HospitalModel
from app.schemas import TransferRecommendationRequest, TransferRecommendationResponse
from app.services.db_adapters import hospital_from_model, resolve_hospital_model
from app.services.transfer_service import TransferService

router = APIRouter()
service = TransferService()


@router.post("/recommend", response_model=TransferRecommendationResponse)
def recommend_transfer(
    request: TransferRecommendationRequest,
    db: Session = Depends(get_db),
) -> TransferRecommendationResponse:
    hospitals = [hospital_from_model(db, row) for row in db.query(HospitalModel).all()]
    origin_row = resolve_hospital_model(db, request.origin_hospital_id)
    if not origin_row:
        raise HTTPException(status_code=404, detail="Origin hospital not found")
    request.origin_hospital_id = origin_row.id
    return service.recommend(request, hospitals_override=hospitals)
