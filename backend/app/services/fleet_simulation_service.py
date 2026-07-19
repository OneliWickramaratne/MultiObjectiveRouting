from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from app.database import SessionLocal
from app.models import AmbulanceModel, HospitalModel, TransferRequestModel
from app.services.osm_graph_routing_service import osm_graph_routing_service
from app.services.route_motion_service import RouteTrack, haversine_m


LOGGER = logging.getLogger(__name__)
MOVING_PICKUP_STATUS = "ambulance_en_route_to_pickup"
MOVING_DESTINATION_STATUS = "en_route_to_destination"
ACTIVE_TRANSFER_STATUSES = {
    "accepted_pending_ambulance",
    "ambulance_assigned",
    MOVING_PICKUP_STATUS,
    "patient_onboard",
    MOVING_DESTINATION_STATUS,
}
SIMULATION_TICK_SECONDS = 0.5


@dataclass
class MotionProgress:
    route_key: str
    track: RouteTrack
    progress_m: float
    speed_mps: float
    navigation_leg: str
    last_tick: float


class FleetSimulationService:
    """Server-authoritative, distance-based ambulance movement on OSM geometry."""

    def __init__(self) -> None:
        self._motion: dict[str, MotionProgress] = {}
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if os.getenv("FLEET_SIMULATION", "1").strip().lower() in {"0", "false", "off"}:
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, daemon=True, name="fleet-simulation")
            self._thread.start()

    def _run(self) -> None:
        self._initialize_fleet()
        while True:
            started = time.monotonic()
            try:
                self._advance_fleet()
            except Exception:
                LOGGER.exception("Fleet simulation tick failed")
            elapsed = time.monotonic() - started
            time.sleep(max(0.05, SIMULATION_TICK_SECONDS - elapsed))

    def _initialize_fleet(self) -> None:
        with SessionLocal() as db:
            active_ids = self._active_transfer_by_ambulance(db)
            hospitals = {hospital.id: hospital for hospital in db.query(HospitalModel).all()}
            for ambulance in db.query(AmbulanceModel).all():
                if ambulance.id in active_ids:
                    continue
                base = hospitals.get(ambulance.base_hospital_id or "")
                if not base:
                    continue
                if ambulance.status == "available" and not self._is_at_base(ambulance, base):
                    continue
                if ambulance.status != "offline":
                    self._park_at_base(ambulance, base)
            db.commit()

    def _advance_fleet(self) -> None:
        with SessionLocal() as db:
            active_by_ambulance = self._active_transfer_by_ambulance(db)
            hospitals = {hospital.id: hospital for hospital in db.query(HospitalModel).all()}
            now = datetime.utcnow()
            for ambulance in db.query(AmbulanceModel).all():
                transfer = active_by_ambulance.get(ambulance.id)
                if transfer:
                    self._advance_active_mission(ambulance, transfer, now)
                    continue
                base = hospitals.get(ambulance.base_hospital_id or "")
                if not base or ambulance.status == "offline":
                    self._motion.pop(ambulance.id, None)
                    continue
                if ambulance.status == "available" and not self._is_at_base(ambulance, base):
                    self._advance_return_to_base(ambulance, base, now)
                elif ambulance.status == "available":
                    self._park_at_base(ambulance, base)
                else:
                    self._set_stationary(ambulance, None, now)
            db.commit()

    def _advance_active_mission(
        self,
        ambulance: AmbulanceModel,
        transfer: TransferRequestModel,
        now: datetime,
    ) -> None:
        if transfer.status == MOVING_PICKUP_STATUS:
            leg = "pickup"
            route_name = "pickup_route"
        elif transfer.status == MOVING_DESTINATION_STATUS:
            leg = "destination"
            route_name = "destination_route"
        else:
            expected_leg = "pickup" if transfer.status == "ambulance_assigned" else "destination"
            self._motion.pop(ambulance.id, None)
            self._set_stationary(ambulance, expected_leg, now)
            return

        payload = self._route_payload(transfer, route_name)
        track = RouteTrack.from_polyline(payload.get("polyline", [])) if payload else None
        if not track:
            self._set_stationary(ambulance, "route_unavailable", now)
            return
        route_key = f"{transfer.id}:{leg}:{len(track.points)}:{round(track.total_m)}"
        duration_seconds = max(float(payload.get("estimated_minutes", 1)) * 60, 30)
        motion = self._ensure_motion(ambulance, route_key, track, leg, duration_seconds)
        self._advance_motion(ambulance, motion, now)

    def _advance_return_to_base(
        self,
        ambulance: AmbulanceModel,
        base: HospitalModel,
        now: datetime,
    ) -> None:
        motion = self._motion.get(ambulance.id)
        if not motion or motion.navigation_leg != "return_to_base":
            route = osm_graph_routing_service.route_coordinates(
                origin_latitude=ambulance.latitude,
                origin_longitude=ambulance.longitude,
                destination_latitude=base.latitude,
                destination_longitude=base.longitude,
                strategy="ml_traffic_risk_aware",
                urgency_class="moderate",
                congestion_ratio=1.0,
            )
            track = RouteTrack.from_polyline(route.polyline) if route else None
            if not track:
                self._park_at_base(ambulance, base)
                return
            duration_seconds = max(route.estimated_seconds, 30)
            route_key = f"return:{ambulance.id}:{len(track.points)}:{round(track.total_m)}"
            motion = self._ensure_motion(
                ambulance,
                route_key,
                track,
                "return_to_base",
                duration_seconds,
            )
        self._advance_motion(ambulance, motion, now)
        if motion.progress_m >= motion.track.total_m - 0.5:
            self._park_at_base(ambulance, base)

    def _ensure_motion(
        self,
        ambulance: AmbulanceModel,
        route_key: str,
        track: RouteTrack,
        leg: str,
        duration_seconds: float,
    ) -> MotionProgress:
        existing = self._motion.get(ambulance.id)
        if existing and existing.route_key == route_key:
            return existing
        projection = track.project(ambulance.latitude, ambulance.longitude)
        stable_hash = int(hashlib.sha256(f"{ambulance.id}:{route_key}".encode()).hexdigest()[:8], 16)
        timing_factor = 0.92 + (stable_hash % 21) / 100
        speed_mps = max(3.5, min((track.total_m / duration_seconds) * timing_factor, 20.0))
        motion = MotionProgress(
            route_key=route_key,
            track=track,
            progress_m=projection.progress_m,
            speed_mps=speed_mps,
            navigation_leg=leg,
            last_tick=time.monotonic(),
        )
        self._motion[ambulance.id] = motion
        ambulance.route_progress_m = motion.progress_m
        ambulance.navigation_leg = leg
        return motion

    def _advance_motion(self, ambulance: AmbulanceModel, motion: MotionProgress, now: datetime) -> None:
        current_tick = time.monotonic()
        elapsed = max(0.0, min(current_tick - motion.last_tick, 1.5))
        motion.last_tick = current_tick
        motion.progress_m = min(motion.track.total_m, motion.progress_m + motion.speed_mps * elapsed)
        latitude, longitude = motion.track.position_at(motion.progress_m)
        ambulance.latitude = latitude
        ambulance.longitude = longitude
        ambulance.route_progress_m = motion.progress_m
        ambulance.heading_degrees = motion.track.heading_at(motion.progress_m)
        ambulance.speed_kph = 0.0 if motion.progress_m >= motion.track.total_m - 0.5 else motion.speed_mps * 3.6
        ambulance.navigation_leg = motion.navigation_leg
        ambulance.telemetry_updated_at = now
        ambulance.updated_at = now

    def _park_at_base(self, ambulance: AmbulanceModel, base: HospitalModel) -> None:
        ambulance.latitude = base.latitude
        ambulance.longitude = base.longitude
        ambulance.speed_kph = 0.0
        ambulance.route_progress_m = 0.0
        ambulance.navigation_leg = None
        ambulance.telemetry_updated_at = datetime.utcnow()
        ambulance.updated_at = datetime.utcnow()
        ambulance.status = "available"
        self._motion.pop(ambulance.id, None)

    def _set_stationary(self, ambulance: AmbulanceModel, leg: str | None, now: datetime) -> None:
        ambulance.speed_kph = 0.0
        ambulance.navigation_leg = leg
        ambulance.telemetry_updated_at = now
        ambulance.updated_at = now

    @staticmethod
    def _route_payload(transfer: TransferRequestModel, route_name: str) -> dict:
        try:
            payload = json.loads(transfer.route_payload_json or "{}")
        except json.JSONDecodeError:
            return {}
        route = payload.get(route_name)
        return route if isinstance(route, dict) else {}

    @staticmethod
    def _is_at_base(ambulance: AmbulanceModel, base: HospitalModel) -> bool:
        return haversine_m(
            (ambulance.latitude, ambulance.longitude),
            (base.latitude, base.longitude),
        ) < 4

    @staticmethod
    def _active_transfer_by_ambulance(db) -> dict[str, TransferRequestModel]:
        transfers = (
            db.query(TransferRequestModel)
            .filter(
                TransferRequestModel.ambulance_id.is_not(None),
                TransferRequestModel.status.in_(ACTIVE_TRANSFER_STATUSES),
            )
            .order_by(TransferRequestModel.updated_at.desc())
            .all()
        )
        result: dict[str, TransferRequestModel] = {}
        for transfer in transfers:
            if transfer.ambulance_id and transfer.ambulance_id not in result:
                result[transfer.ambulance_id] = transfer
        return result


fleet_simulation_service = FleetSimulationService()
