from app.schemas import UrgencyPredictionRequest, UrgencyPredictionResponse


class UrgencyService:
    """Rule-based MVP with the same interface a trained model will use."""

    def predict(self, request: UrgencyPredictionRequest) -> UrgencyPredictionResponse:
        score = 0.2
        explanation: list[str] = []

        if request.condition_type in {"cardiac", "trauma", "respiratory", "sepsis"}:
            score += 0.15
            explanation.append("High-risk condition category")

        if request.oxygen_saturation_band == "critical":
            score += 0.3
            explanation.append("Critical oxygen saturation")
        elif request.oxygen_saturation_band == "low":
            score += 0.2
            explanation.append("Low oxygen saturation")

        if request.blood_pressure_band == "shock":
            score += 0.25
            explanation.append("Blood pressure indicates shock")
        elif request.blood_pressure_band == "unstable":
            score += 0.15
            explanation.append("Unstable blood pressure")

        if request.consciousness_level == "unconscious":
            score += 0.2
            explanation.append("Patient unconscious")
        elif request.consciousness_level == "reduced":
            score += 0.1
            explanation.append("Reduced consciousness")

        if request.ventilator_required:
            score += 0.2
            explanation.append("Ventilator required")

        score = min(score, 1.0)
        if score >= 0.75:
            urgency_class = "critical"
        elif score >= 0.5:
            urgency_class = "high"
        else:
            urgency_class = "moderate"

        if not explanation:
            explanation.append("No severe risk factor selected")

        return UrgencyPredictionResponse(
            urgency_class=urgency_class,
            urgency_score=round(score, 2),
            explanation=explanation,
        )
