from app.data_store import HOSPITALS, Hospital, get_hospital, hospital_supports_condition, normalize_icu_type
from app.schemas import (
    HospitalRecommendation,
    TransferRecommendationRequest,
    TransferRecommendationResponse,
    UrgencyPredictionRequest,
)
from app.services.routing_service import RoutingService
from app.services.urgency_service import UrgencyService
from app.services.db_adapters import get_hospital_from_list


class TransferService:
    def __init__(self) -> None:
        self.urgency_service = UrgencyService()
        self.routing_service = RoutingService()

    def recommend(
        self,
        request: TransferRecommendationRequest,
        hospitals_override: list[Hospital] | None = None,
    ) -> TransferRecommendationResponse:
        hospitals = hospitals_override or HOSPITALS
        origin = (
            get_hospital_from_list(hospitals, request.origin_hospital_id)
            if hospitals_override
            else get_hospital(request.origin_hospital_id)
        )
        if origin is None:
            raise ValueError("Origin hospital not found")

        urgency = self.urgency_service.predict(
            UrgencyPredictionRequest(
                **request.patient_condition.model_dump(),
                required_icu_type=request.required_icu_type,
            )
        )

        normalized_icu_type = normalize_icu_type(request.required_icu_type)

        candidates = [
            hospital
            for hospital in hospitals
            if hospital.id != origin.id
            and normalized_icu_type in hospital.icu_types
            and hospital.available_beds_for(normalized_icu_type) > 0
            and hospital_supports_condition(hospital, request.patient_condition.condition_type)
            and (
                not request.patient_condition.ventilator_required
                or hospital.has_ventilator_support
            )
        ]

        recommendations: list[HospitalRecommendation] = []
        for hospital in candidates:
            route_options = self.routing_service.compare_routes(origin, hospital, urgency.urgency_class)
            best_route = next(
                route for route in route_options if route.strategy == "ml_traffic_risk_aware"
            )
            ward_available = hospital.available_beds_for(normalized_icu_type)
            ward_total = hospital.total_beds_for(normalized_icu_type)
            capacity_score = min(ward_available / max(ward_total, 1), 1.0)
            score = 1 - best_route.total_cost + (capacity_score * 0.15)
            recommendations.append(
                HospitalRecommendation(
                    destination_hospital_id=hospital.id,
                    destination_name=hospital.name,
                    rank=0,
                    score=round(score, 3),
                    available_beds=ward_available,
                    estimated_minutes=best_route.estimated_minutes,
                    route_risk_score=best_route.risk_score,
                    reasons=[
                        "Matching ICU capability",
                        f"{ward_available} {normalized_icu_type} bed(s) available",
                        f"Selected {best_route.strategy} route by urgency-adjusted cost",
                    ],
                )
            )

        recommendations.sort(key=lambda item: item.score, reverse=True)
        for index, item in enumerate(recommendations, start=1):
            item.rank = index

        return TransferRecommendationResponse(
            urgency_class=urgency.urgency_class,
            urgency_score=urgency.urgency_score,
            recommendations=recommendations,
        )
