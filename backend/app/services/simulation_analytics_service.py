from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import AmbulanceModel
from app.services.capacity_forecast_service import HospitalCapacityForecast
from app.time_utils import utcnow


@dataclass(frozen=True)
class ScenarioProfile:
    key: str
    label: str
    arrivals_per_hospital_6h: float
    critical_share: float
    ambulance_factor: float
    description: str


class SimulationAnalyticsService:
    profiles = {
        "baseline": ScenarioProfile(
            key="baseline",
            label="Baseline demand",
            arrivals_per_hospital_6h=0.35,
            critical_share=0.22,
            ambulance_factor=0.5,
            description="Normal transfer pressure using current capacity and fleet readiness.",
        ),
        "evening_surge": ScenarioProfile(
            key="evening_surge",
            label="Evening surge",
            arrivals_per_hospital_6h=0.9,
            critical_share=0.34,
            ambulance_factor=0.58,
            description="Higher transfer load during evening congestion and reduced bed turnover.",
        ),
        "mass_casualty": ScenarioProfile(
            key="mass_casualty",
            label="Mass casualty",
            arrivals_per_hospital_6h=1.85,
            critical_share=0.66,
            ambulance_factor=0.78,
            description="High acuity multi-patient event requiring rapid ambulance and ICU coordination.",
        ),
        "respiratory_wave": ScenarioProfile(
            key="respiratory_wave",
            label="Respiratory wave",
            arrivals_per_hospital_6h=1.25,
            critical_share=0.48,
            ambulance_factor=0.62,
            description="Ventilator-heavy ICU pressure with slower discharge confidence.",
        ),
    }

    def run(
        self,
        db: Session,
        forecasts: list[HospitalCapacityForecast],
        scenario: str,
        duration_hours: int,
        intensity: float,
    ) -> dict:
        profile = self.profiles.get(scenario, self.profiles["baseline"])
        safe_hours = max(1, min(duration_hours, 24))
        safe_intensity = max(0.25, min(intensity, 3.0))
        total_beds = sum(forecast.total_beds for forecast in forecasts)
        total_available = sum(forecast.current_available_beds for forecast in forecasts)
        available_ambulances = (
            db.query(AmbulanceModel)
            .filter(AmbulanceModel.status == "available")
            .count()
        )

        simulated_transfers = round(
            len(forecasts)
            * profile.arrivals_per_hospital_6h
            * (safe_hours / 6)
            * safe_intensity
        )
        simulated_transfers = max(0, simulated_transfers)
        critical_transfers = math.ceil(simulated_transfers * profile.critical_share)
        ambulances_required = math.ceil(simulated_transfers * profile.ambulance_factor)

        hospital_impacts = self._hospital_impacts(
            forecasts=forecasts,
            total_arrivals=simulated_transfers,
            duration_hours=safe_hours,
            scenario=profile.key,
        )
        shortage_hospitals = sum(1 for impact in hospital_impacts if impact["shortage_beds"] > 0)
        total_shortage_beds = sum(impact["shortage_beds"] for impact in hospital_impacts)
        worst_pressure = max((impact["pressure_score"] for impact in hospital_impacts), default=0.0)
        network_level = self._pressure_level(worst_pressure, total_shortage_beds)

        return {
            "generated_at": utcnow().isoformat(),
            "scenario": profile.key,
            "scenario_label": profile.label,
            "description": profile.description,
            "duration_hours": safe_hours,
            "intensity": round(safe_intensity, 2),
            "simulated_transfers": simulated_transfers,
            "critical_transfers": critical_transfers,
            "ambulances_required": ambulances_required,
            "available_ambulances": available_ambulances,
            "ambulance_gap": max(0, ambulances_required - available_ambulances),
            "total_available_beds": total_available,
            "total_beds": total_beds,
            "shortage_hospitals": shortage_hospitals,
            "total_shortage_beds": total_shortage_beds,
            "network_pressure_level": network_level,
            "network_pressure_score": round(worst_pressure, 3),
            "recommended_action": self._recommended_action(
                network_level=network_level,
                ambulance_gap=max(0, ambulances_required - available_ambulances),
                shortage_beds=total_shortage_beds,
            ),
            "hospital_impacts": hospital_impacts,
        }

    def _hospital_impacts(
        self,
        forecasts: list[HospitalCapacityForecast],
        total_arrivals: int,
        duration_hours: int,
        scenario: str,
    ) -> list[dict]:
        if not forecasts:
            return []
        total_weight = sum(self._hospital_weight(forecast, scenario) for forecast in forecasts)
        remaining_arrivals = total_arrivals
        impacts: list[dict] = []

        for index, forecast in enumerate(forecasts):
            weight = self._hospital_weight(forecast, scenario)
            if index == len(forecasts) - 1:
                # Rounding the earlier shares can overshoot the total; without the
                # clamp the remainder goes negative and *adds* beds to this hospital.
                projected_arrivals = max(0, remaining_arrivals)
            else:
                projected_arrivals = round(total_arrivals * weight / max(total_weight, 1))
                remaining_arrivals -= projected_arrivals
            releases = (
                forecast.expected_discharges_12h
                + forecast.expected_cleaning_recoveries_12h
            ) * (duration_hours / 12)
            raw_available = forecast.current_available_beds - projected_arrivals + releases
            predicted_available = max(0, min(forecast.total_beds, round(raw_available)))
            shortage_beds = max(0, math.ceil(-raw_available))
            predicted_occupied = forecast.total_beds - predicted_available
            pressure_score = predicted_occupied / max(forecast.total_beds, 1)
            impacts.append(
                {
                    "hospital_id": forecast.hospital_id,
                    "hospital_name": forecast.hospital_name,
                    "current_available_beds": forecast.current_available_beds,
                    "projected_arrivals": max(0, projected_arrivals),
                    "projected_releases": round(releases, 1),
                    "predicted_available_beds": predicted_available,
                    "shortage_beds": shortage_beds,
                    "pressure_score": round(pressure_score, 3),
                    "pressure_level": self._pressure_level(pressure_score, shortage_beds),
                    "recommended_action": self._hospital_action(pressure_score, shortage_beds),
                }
            )
        return sorted(
            impacts,
            key=lambda impact: (impact["shortage_beds"], impact["pressure_score"]),
            reverse=True,
        )

    @staticmethod
    def _hospital_weight(forecast: HospitalCapacityForecast, scenario: str) -> float:
        capacity_weight = max(forecast.current_available_beds, 1)
        size_weight = max(forecast.total_beds, 1) / 10
        if scenario == "mass_casualty":
            return (capacity_weight * 0.45) + (size_weight * 0.55)
        if scenario == "respiratory_wave":
            return (capacity_weight * 0.65) + (size_weight * 0.35)
        return (capacity_weight * 0.75) + (size_weight * 0.25)

    @staticmethod
    def _pressure_level(score: float, shortage_beds: int = 0) -> str:
        if shortage_beds > 0 or score >= 0.95:
            return "critical"
        if score >= 0.85:
            return "high"
        if score >= 0.72:
            return "elevated"
        return "stable"

    @staticmethod
    def _hospital_action(score: float, shortage_beds: int) -> str:
        if shortage_beds > 0:
            return f"Open or divert {shortage_beds} ICU bed(s) before accepting more transfers."
        if score >= 0.85:
            return "Accept only high-urgency transfers and accelerate bed turnover."
        if score >= 0.72:
            return "Monitor inbound demand and keep one bed protected for critical cases."
        return "Can continue normal transfer acceptance."

    @staticmethod
    def _recommended_action(network_level: str, ambulance_gap: int, shortage_beds: int) -> str:
        if shortage_beds > 0:
            return "Scenario creates ICU shortage. Activate surge beds, divert stable patients, and pre-alert receiving teams."
        if ambulance_gap > 0:
            return f"Fleet gap of {ambulance_gap} ambulance(s). Reposition available crews before scenario peak."
        if network_level in {"critical", "high"}:
            return "High pressure forecast. Reserve capacity for critical transfers and tighten dispatch thresholds."
        if network_level == "elevated":
            return "Elevated pressure. Use risk-aware routing and prefer hospitals with 6h bed resilience."
        return "Scenario is manageable with current beds and fleet readiness."
