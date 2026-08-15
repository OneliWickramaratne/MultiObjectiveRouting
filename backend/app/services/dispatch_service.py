from __future__ import annotations

import json
import math
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import AmbulanceModel, HospitalModel, TransferRequestModel
from app.services.db_adapters import hospital_from_model
from app.services.osm_graph_routing_service import OSMGraphRoute, osm_graph_routing_service
from app.services.resource_claim_service import claim_available_ambulance
from app.services.traffic_model_service import TrafficModelService
from app.services.transfer_state_machine import TRANSFER_AMBULANCE_ASSIGNED, transition_transfer_atomic
from app.time_utils import utcnow


traffic_model_service = TrafficModelService()


@dataclass(frozen=True)
class DispatchResult:
    ambulance: AmbulanceModel
    score: float
    distance_to_pickup_km: float
    estimated_pickup_minutes: float
    pickup_risk_score: float
    coverage_penalty: float
    urgency_weight: float
    base_match_bonus: float
    stale_location_penalty: float
    explanation: list[str]
    score_components: dict
    pickup_route: OSMGraphRoute | None = None


class DispatchService:
    def __init__(self) -> None:
        self.osm_graph = osm_graph_routing_service
        self.traffic_model = traffic_model_service

    def auto_assign(self, db: Session, transfer: TransferRequestModel) -> DispatchResult | None:
        origin = db.get(HospitalModel, transfer.origin_hospital_id)
        destination = db.get(HospitalModel, transfer.destination_hospital_id)
        if not origin or not destination:
            return None

        available = (
            db.query(AmbulanceModel)
            .filter(AmbulanceModel.status == "available")
            .all()
        )
        if not available:
            return None

        origin_hospital = hospital_from_model(db, origin)
        destination_hospital = hospital_from_model(db, destination)
        traffic_prediction = self.traffic_model.predict(origin_hospital, destination_hospital)
        nearest_candidates = sorted(
            available,
            key=lambda ambulance: self._haversine_km(
                ambulance.latitude,
                ambulance.longitude,
                origin.latitude,
                origin.longitude,
            ),
        )[:8]
        ranked = sorted(
            (
                self._score_ambulance(
                    db,
                    ambulance,
                    origin,
                    transfer.urgency_class,
                    traffic_prediction.congestion_ratio,
                )
                for ambulance in nearest_candidates
            ),
            key=lambda item: item.score,
        )
        destination_route = self.osm_graph.route(
            origin_hospital,
            destination_hospital,
            "ml_traffic_risk_aware",
            transfer.urgency_class,
            traffic_prediction.congestion_ratio,
        )
        transfer_distance_km = (
            destination_route.distance_km
            if destination_route
            else self._haversine_km(
                origin.latitude,
                origin.longitude,
                destination.latitude,
                destination.longitude,
            )
        )
        claimed_ambulance_id = claim_available_ambulance(
            db,
            [item.ambulance.id for item in ranked],
        )
        if not claimed_ambulance_id:
            return None
        selected = next(
            item for item in ranked if item.ambulance.id == claimed_ambulance_id
        )
        selected.ambulance.status = "assigned"
        pickup_route_payload = self._route_payload(
            selected.pickup_route,
            fallback_start=(selected.ambulance.latitude, selected.ambulance.longitude),
            fallback_end=(origin.latitude, origin.longitude),
            fallback_distance_km=selected.distance_to_pickup_km,
            fallback_source="instant_dispatch_pickup_polyline",
        )
        destination_route_payload = self._route_payload(
            destination_route,
            fallback_start=(origin.latitude, origin.longitude),
            fallback_end=(destination.latitude, destination.longitude),
            fallback_distance_km=transfer_distance_km,
            fallback_source="instant_dispatch_polyline",
        )

        transfer.ambulance_id = selected.ambulance.id
        transition_transfer_atomic(db, transfer, TRANSFER_AMBULANCE_ASSIGNED)
        transfer.pickup_latitude = origin.latitude
        transfer.pickup_longitude = origin.longitude
        transfer.dropoff_latitude = destination.latitude
        transfer.dropoff_longitude = destination.longitude
        transfer.route_payload_json = json.dumps(
            {
                "dispatch": {
                    "model": "coverage_risk_eta_dispatch_v2",
                    "score": round(selected.score, 4),
                    "distance_to_pickup_km": round(selected.distance_to_pickup_km, 3),
                    "estimated_pickup_minutes": round(selected.estimated_pickup_minutes, 1),
                    "pickup_risk_score": round(selected.pickup_risk_score, 3),
                    "coverage_penalty": round(selected.coverage_penalty, 3),
                    "urgency_weight": round(selected.urgency_weight, 3),
                    "base_match_bonus": round(selected.base_match_bonus, 3),
                    "stale_location_penalty": round(selected.stale_location_penalty, 3),
                    "routing_source": pickup_route_payload["source"],
                    "score_components": selected.score_components,
                    "explanation": selected.explanation,
                    "candidate_rankings": [
                        {
                            "ambulance_id": item.ambulance.id,
                            "call_sign": item.ambulance.call_sign,
                            "base_hospital_id": item.ambulance.base_hospital_id,
                            "score": round(item.score, 4),
                            "estimated_pickup_minutes": round(item.estimated_pickup_minutes, 1),
                            "distance_to_pickup_km": round(item.distance_to_pickup_km, 3),
                            "pickup_risk_score": round(item.pickup_risk_score, 3),
                            "coverage_penalty": round(item.coverage_penalty, 3),
                            "reasons": item.explanation,
                        }
                        for item in ranked[:5]
                    ],
                },
                "pickup_route": pickup_route_payload,
                "destination_route": destination_route_payload,
                # Retained for compatibility with older frontends.
                "mission_route": destination_route_payload,
            }
        )
        return selected

    def _score_ambulance(
        self,
        db: Session,
        ambulance: AmbulanceModel,
        origin: HospitalModel,
        urgency_class: str,
        congestion_ratio: float,
    ) -> DispatchResult:
        direct_distance = self._haversine_km(
            ambulance.latitude,
            ambulance.longitude,
            origin.latitude,
            origin.longitude,
        )
        graph_route = self.osm_graph.route_coordinates(
            origin_latitude=ambulance.latitude,
            origin_longitude=ambulance.longitude,
            destination_latitude=origin.latitude,
            destination_longitude=origin.longitude,
            strategy="ml_traffic_risk_aware",
            urgency_class=urgency_class,
            congestion_ratio=congestion_ratio,
        )
        distance = graph_route.distance_km if graph_route else direct_distance
        estimated_minutes = graph_route.estimated_seconds / 60 if graph_route else (distance / 35) * 60
        pickup_risk = graph_route.risk_score if graph_route else 0.45
        urgency_weight = self._urgency_weight(urgency_class)
        risk_weight = 2.7 if urgency_class == "critical" else 3.4 if urgency_class == "high" else 4.1
        coverage_weight = 2.0 if urgency_class == "critical" else 3.3 if urgency_class == "high" else 4.6
        coverage_penalty = self._coverage_penalty(db, ambulance)
        base_match_bonus = -1.15 if ambulance.base_hospital_id == origin.id else 0.0
        stale_location_penalty = self._stale_location_penalty(ambulance)
        off_base_penalty = self._off_base_penalty(db, ambulance)
        score_components = {
            "eta_cost": round(estimated_minutes * urgency_weight, 4),
            "risk_cost": round(pickup_risk * risk_weight, 4),
            "coverage_cost": round(coverage_penalty * coverage_weight, 4),
            "base_match_bonus": round(base_match_bonus, 4),
            "stale_location_penalty": round(stale_location_penalty, 4),
            "off_base_penalty": round(off_base_penalty, 4),
        }
        score = sum(score_components.values())
        explanation = self._dispatch_explanation(
            ambulance,
            origin,
            estimated_minutes,
            pickup_risk,
            coverage_penalty,
            base_match_bonus,
            stale_location_penalty,
            graph_route is not None,
        )
        return DispatchResult(
            ambulance=ambulance,
            score=score,
            distance_to_pickup_km=distance,
            estimated_pickup_minutes=estimated_minutes,
            pickup_risk_score=pickup_risk,
            coverage_penalty=coverage_penalty,
            urgency_weight=urgency_weight,
            base_match_bonus=base_match_bonus,
            stale_location_penalty=stale_location_penalty,
            explanation=explanation,
            score_components=score_components,
            pickup_route=graph_route,
        )

    @staticmethod
    def _urgency_weight(urgency_class: str) -> float:
        return {
            "critical": 1.0,
            "high": 1.15,
            "moderate": 1.35,
            "low": 1.55,
        }.get(urgency_class, 1.2)

    @staticmethod
    def _coverage_penalty(db: Session, ambulance: AmbulanceModel) -> float:
        if not ambulance.base_hospital_id:
            return 0.55
        available_at_base = (
            db.query(AmbulanceModel)
            .filter(
                AmbulanceModel.base_hospital_id == ambulance.base_hospital_id,
                AmbulanceModel.status == "available",
            )
            .count()
        )
        if available_at_base <= 1:
            return 1.0
        if available_at_base == 2:
            return 0.45
        return 0.12

    @staticmethod
    def _stale_location_penalty(ambulance: AmbulanceModel) -> float:
        if not ambulance.updated_at:
            return 0.35
        age_minutes = max((utcnow() - ambulance.updated_at).total_seconds() / 60, 0)
        if age_minutes > 30:
            return 0.5
        if age_minutes > 10:
            return 0.2
        return 0.0

    def _off_base_penalty(self, db: Session, ambulance: AmbulanceModel) -> float:
        if not ambulance.base_hospital_id:
            return 0.2
        base = db.get(HospitalModel, ambulance.base_hospital_id)
        if not base:
            return 0.2
        distance_from_base = self._haversine_km(ambulance.latitude, ambulance.longitude, base.latitude, base.longitude)
        return min(distance_from_base / 15, 0.6)

    @staticmethod
    def _dispatch_explanation(
        ambulance: AmbulanceModel,
        origin: HospitalModel,
        estimated_minutes: float,
        pickup_risk: float,
        coverage_penalty: float,
        base_match_bonus: float,
        stale_location_penalty: float,
        graph_route_used: bool,
    ) -> list[str]:
        reasons = [
            f"Pickup ETA {estimated_minutes:.1f} min",
            f"Pickup route risk {pickup_risk:.2f}",
        ]
        if graph_route_used:
            reasons.append("Used local OSM graph route to pickup")
        else:
            reasons.append("Used fallback direct pickup estimate")
        if base_match_bonus < 0:
            reasons.append("Ambulance is based at the requesting hospital")
        if coverage_penalty >= 1:
            reasons.append("Coverage warning: assigning this unit leaves its base with no spare ambulance")
        elif coverage_penalty <= 0.2:
            reasons.append("Low coverage impact at ambulance base")
        if stale_location_penalty:
            reasons.append("Location update is stale, score penalized")
        if ambulance.base_hospital_id and ambulance.base_hospital_id != origin.id:
            reasons.append("Cross-base dispatch selected because total score was better")
        return reasons

    @staticmethod
    def _route_payload(
        route: OSMGraphRoute | None,
        fallback_start: tuple[float, float],
        fallback_end: tuple[float, float],
        fallback_distance_km: float,
        fallback_source: str,
    ) -> dict:
        if route:
            return {
                "source": "local_osm_graph_ml_weighted",
                "strategy": "ml_traffic_risk_aware",
                "distance_km": route.distance_km,
                "estimated_minutes": round(route.estimated_seconds / 60, 1),
                "risk_score": route.risk_score,
                "route_nodes": route.node_ids,
                "route_steps": [
                    {
                        "start_index": step.start_index,
                        "end_index": step.end_index,
                        "road_name": step.road_name,
                        "maneuver": step.maneuver,
                        "distance_meters": step.distance_meters,
                        "estimated_seconds": step.estimated_seconds,
                        "average_risk": step.average_risk,
                        "instruction": step.instruction,
                    }
                    for step in route.route_steps
                ],
                "risk_features": route.risk_features,
                "risk_factors": route.risk_factors,
                "explanation": route.explanation,
                "polyline": route.polyline,
            }
        return {
            "source": fallback_source,
            "strategy": "legacy_fallback",
            "distance_km": round(fallback_distance_km, 3),
            "estimated_minutes": round((fallback_distance_km / 35) * 60, 1),
            "risk_score": None,
            "route_nodes": [],
            "route_steps": [
                {
                    "start_index": 0,
                    "end_index": 1,
                    "road_name": "direct fallback corridor",
                    "maneuver": "depart",
                    "distance_meters": round(fallback_distance_km * 1000, 1),
                    "estimated_seconds": round((fallback_distance_km / 35) * 3600, 1),
                    "average_risk": None,
                    "instruction": f"Depart toward destination for {fallback_distance_km:.1f} km",
                }
            ],
            "risk_features": {},
            "risk_factors": ["Fallback route: OSM graph path unavailable"],
            "explanation": ["Fallback route generated from direct coordinates"],
            "polyline": [
                [fallback_start[0], fallback_start[1]],
                [fallback_end[0], fallback_end[1]],
            ],
        }

    @staticmethod
    def route_payload_for_coordinates(
        start: tuple[float, float],
        end: tuple[float, float],
        urgency_class: str,
        fallback_source: str,
    ) -> dict:
        route = osm_graph_routing_service.route_coordinates(
            origin_latitude=start[0],
            origin_longitude=start[1],
            destination_latitude=end[0],
            destination_longitude=end[1],
            strategy="ml_traffic_risk_aware",
            urgency_class=urgency_class,
            congestion_ratio=1.0,
        )
        fallback_distance_km = DispatchService._haversine_km(start[0], start[1], end[0], end[1])
        return DispatchService._route_payload(
            route,
            fallback_start=start,
            fallback_end=end,
            fallback_distance_km=fallback_distance_km,
            fallback_source=fallback_source,
        )

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        earth_radius_km = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return earth_radius_km * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))
