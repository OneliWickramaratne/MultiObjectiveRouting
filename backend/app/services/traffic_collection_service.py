from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

import requests

from app.data_store import HOSPITALS, get_hospital
from app.schemas import TrafficSnapshotRequest
from app.time_utils import utcnow


COMPUTE_ROUTE_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
FIELD_MASK = ",".join(
    [
        "originIndex",
        "destinationIndex",
        "status",
        "condition",
        "distanceMeters",
        "duration",
        "staticDuration",
    ]
)


class TrafficCollectionService:
    """Collect Google Routes API snapshots for later model retraining."""

    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[3]
        self.output_path = self.project_root / "data" / "traffic_observations_live.csv"
        self.api_key = os.getenv("GOOGLE_MAPS_API_KEY")

    def collect_snapshot(self, request: TrafficSnapshotRequest) -> dict[str, object]:
        if not self.api_key:
            return {
                "collected_rows": 0,
                "output_path": str(self.output_path),
                "google_api_enabled": False,
                "message": "GOOGLE_MAPS_API_KEY is not set. Snapshot collection was skipped.",
            }

        origins = self._select_hospitals(request.origin_hospital_ids)
        destinations = self._select_hospitals(request.destination_hospital_ids)
        elements = self._call_google_matrix(origins, destinations, request.departure_time_iso)
        rows = self._flatten_elements(origins, destinations, elements)
        self._append_rows(rows)
        return {
            "collected_rows": len(rows),
            "output_path": str(self.output_path),
            "google_api_enabled": True,
            "message": f"Collected {len(rows)} Google traffic observations.",
        }

    def _select_hospitals(self, ids: list[str] | None):
        if not ids:
            return HOSPITALS
        selected = [get_hospital(hospital_id) for hospital_id in ids]
        return [hospital for hospital in selected if hospital is not None]

    def _call_google_matrix(self, origins, destinations, departure_time_iso: str | None) -> list[dict[str, Any]]:
        payload = {
            "origins": [self._waypoint(hospital) for hospital in origins],
            "destinations": [self._waypoint(hospital) for hospital in destinations],
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
            "units": "METRIC",
            "languageCode": "en-US",
            "departureTime": departure_time_iso
            or utcnow().replace(microsecond=0).isoformat() + "Z",
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key or "",
            "X-Goog-FieldMask": FIELD_MASK,
        }
        response = requests.post(
            COMPUTE_ROUTE_MATRIX_URL,
            headers=headers,
            json=payload,
            timeout=30,
            stream=True,
        )
        response.raise_for_status()

        elements: list[dict[str, Any]] = []
        for line in response.iter_lines():
            if line:
                elements.append(json.loads(line.decode("utf-8")))
        return elements

    def _flatten_elements(self, origins, destinations, elements: list[dict[str, Any]]) -> list[dict[str, object]]:
        request_time_utc = utcnow().replace(microsecond=0).isoformat() + "Z"
        rows: list[dict[str, object]] = []
        for element in elements:
            origin_index = int(element.get("originIndex", -1))
            destination_index = int(element.get("destinationIndex", -1))
            if origin_index < 0 or destination_index < 0:
                continue
            if origin_index >= len(origins) or destination_index >= len(destinations):
                continue

            origin = origins[origin_index]
            destination = destinations[destination_index]
            duration_seconds = self._duration_seconds(element.get("duration"))
            static_seconds = self._duration_seconds(element.get("staticDuration"))
            status = element.get("status", {})
            rows.append(
                {
                    "request_time_utc": request_time_utc,
                    "origin_hospital_id": origin.id,
                    "origin_hospital_name": origin.name,
                    "destination_hospital_id": destination.id,
                    "destination_hospital_name": destination.name,
                    "status_code": status.get("code", "OK") if isinstance(status, dict) else str(status),
                    "condition": element.get("condition"),
                    "distanceMeters": element.get("distanceMeters"),
                    "duration_seconds": duration_seconds,
                    "static_duration_seconds": static_seconds,
                    "congestion_ratio": (
                        round(duration_seconds / static_seconds, 4)
                        if duration_seconds and static_seconds
                        else None
                    ),
                    "label_source": "live_google_routes_api",
                }
            )
        return rows

    def _append_rows(self, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(rows[0].keys())
        write_header = not self.output_path.exists()
        with self.output_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _waypoint(hospital) -> dict[str, Any]:
        return {
            "waypoint": {
                "location": {
                    "latLng": {
                        "latitude": hospital.latitude,
                        "longitude": hospital.longitude,
                    }
                }
            }
        }

    @staticmethod
    def _duration_seconds(value: str | None) -> float | None:
        if not value:
            return None
        if value.endswith("s"):
            return float(value[:-1])
        return None
