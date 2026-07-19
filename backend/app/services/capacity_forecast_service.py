from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import BedLifecycleEventModel, HospitalModel, ICUBedModel, TransferRequestModel


@dataclass(frozen=True)
class CapacityForecastPoint:
    horizon_hours: int
    predicted_available_beds: int
    predicted_occupied_beds: int
    pressure_score: float
    pressure_level: str


@dataclass(frozen=True)
class HospitalCapacityForecast:
    hospital_id: str
    hospital_name: str
    total_beds: int
    current_available_beds: int
    current_occupied_beds: int
    inbound_transfers: int
    expected_discharges_12h: float
    expected_cleaning_recoveries_12h: float
    points: list[CapacityForecastPoint]
    recommended_action: str


class CapacityForecastService:
    horizons = (1, 3, 6, 12)

    def forecast_network(self, db: Session) -> list[HospitalCapacityForecast]:
        hospitals = db.query(HospitalModel).order_by(HospitalModel.id).all()
        return [self.forecast_hospital(db, hospital) for hospital in hospitals]

    def forecast_hospital(self, db: Session, hospital: HospitalModel) -> HospitalCapacityForecast:
        beds = db.query(ICUBedModel).filter(ICUBedModel.hospital_id == hospital.id).all()
        total_beds = len(beds) or hospital.total_beds
        current_available = sum(1 for bed in beds if bed.status == "available")
        current_occupied = max(total_beds - current_available, 0)
        inbound_transfers = self._active_inbound_transfers(db, hospital.id)
        discharge_rate_12h = self._recent_bed_release_rate(db, hospital.id)
        cleaning_recovery_12h = self._cleaning_recovery_capacity(beds)

        points: list[CapacityForecastPoint] = []
        for horizon in self.horizons:
            fraction = horizon / 12
            expected_arrivals = inbound_transfers * min(1.0, horizon / 3)
            expected_releases = (discharge_rate_12h + cleaning_recovery_12h) * fraction
            predicted_available = round(current_available - expected_arrivals + expected_releases)
            predicted_available = max(0, min(total_beds, predicted_available))
            predicted_occupied = total_beds - predicted_available
            pressure_score = predicted_occupied / max(total_beds, 1)
            points.append(
                CapacityForecastPoint(
                    horizon_hours=horizon,
                    predicted_available_beds=predicted_available,
                    predicted_occupied_beds=predicted_occupied,
                    pressure_score=round(pressure_score, 3),
                    pressure_level=self._pressure_level(pressure_score),
                )
            )

        return HospitalCapacityForecast(
            hospital_id=hospital.id,
            hospital_name=hospital.name,
            total_beds=total_beds,
            current_available_beds=current_available,
            current_occupied_beds=current_occupied,
            inbound_transfers=inbound_transfers,
            expected_discharges_12h=round(discharge_rate_12h, 2),
            expected_cleaning_recoveries_12h=round(cleaning_recovery_12h, 2),
            points=points,
            recommended_action=self._recommended_action(points),
        )

    @staticmethod
    def _active_inbound_transfers(db: Session, hospital_id: str) -> int:
        active_statuses = {
            "pending_destination_acceptance",
            "accepted_pending_ambulance",
            "ambulance_assigned",
            "ambulance_en_route_to_pickup",
            "en_route_to_destination",
        }
        return (
            db.query(TransferRequestModel)
            .filter(
                TransferRequestModel.destination_hospital_id == hospital_id,
                TransferRequestModel.status.in_(active_statuses),
            )
            .count()
        )

    @staticmethod
    def _recent_bed_release_rate(db: Session, hospital_id: str) -> float:
        since = datetime.utcnow() - timedelta(hours=48)
        releases = (
            db.query(BedLifecycleEventModel)
            .filter(
                BedLifecycleEventModel.hospital_id == hospital_id,
                BedLifecycleEventModel.new_status == "available",
                BedLifecycleEventModel.created_at >= since,
            )
            .count()
        )
        if releases == 0:
            return 0.5
        return max(0.5, min(releases / 4, 6.0))

    @staticmethod
    def _cleaning_recovery_capacity(beds: list[ICUBedModel]) -> float:
        cleaning = sum(1 for bed in beds if bed.status == "cleaning")
        return min(cleaning, 4) * 0.8

    @staticmethod
    def _pressure_level(score: float) -> str:
        if score >= 0.95:
            return "critical"
        if score >= 0.85:
            return "high"
        if score >= 0.72:
            return "elevated"
        return "stable"

    @staticmethod
    def _recommended_action(points: list[CapacityForecastPoint]) -> str:
        worst = max(points, key=lambda point: point.pressure_score)
        if worst.pressure_level == "critical":
            return "Divert non-critical transfers and prepare surge capacity."
        if worst.pressure_level == "high":
            return "Accept critical transfers only; expedite discharge and cleaning workflow."
        if worst.pressure_level == "elevated":
            return "Monitor closely and prefer destinations with stronger 6h availability."
        return "Capacity is stable for normal risk-aware transfers."
