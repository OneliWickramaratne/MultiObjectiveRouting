from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

from app.data_store import Hospital


COMPUTE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = ",".join(
    [
        "routes.distanceMeters",
        "routes.duration",
        "routes.staticDuration",
        "routes.polyline.encodedPolyline",
        "routes.routeLabels",
    ]
)


@dataclass(frozen=True)
class GoogleRoute:
    distance_km: float
    duration_seconds: float
    static_duration_seconds: float
    congestion_ratio: float
    polyline: list[list[float]]


class GoogleRoutesService:
    def __init__(self) -> None:
        self.api_key = os.getenv("GOOGLE_MAPS_API_KEY")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def get_route(
        self,
        origin: Hospital,
        destination: Hospital,
        strategy: str,
    ) -> GoogleRoute | None:
        if not self.enabled:
            return None

        routing_preference = (
            "TRAFFIC_AWARE_OPTIMAL"
            if strategy == "ml_traffic_risk_aware"
            else "TRAFFIC_AWARE"
        )
        payload = {
            "origin": self._waypoint(origin),
            "destination": self._waypoint(destination),
            "travelMode": "DRIVE",
            "routingPreference": routing_preference,
            "computeAlternativeRoutes": strategy == "ml_traffic_risk_aware",
            "units": "METRIC",
            "languageCode": "en-US",
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key or "",
            "X-Goog-FieldMask": FIELD_MASK,
        }

        try:
            response = requests.post(
                COMPUTE_ROUTES_URL,
                headers=headers,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            routes = response.json().get("routes", [])
            if not routes:
                return None
            selected = routes[0]
            return self._parse_route(selected)
        except requests.RequestException:
            return None
        except (KeyError, TypeError, ValueError):
            return None

    def _parse_route(self, route: dict[str, Any]) -> GoogleRoute:
        distance_meters = float(route["distanceMeters"])
        duration_seconds = self._parse_duration_seconds(route["duration"])
        static_duration_seconds = self._parse_duration_seconds(route["staticDuration"])
        encoded_polyline = route.get("polyline", {}).get("encodedPolyline", "")
        polyline = self.decode_polyline(encoded_polyline) if encoded_polyline else []
        return GoogleRoute(
            distance_km=round(distance_meters / 1000, 3),
            duration_seconds=duration_seconds,
            static_duration_seconds=static_duration_seconds,
            congestion_ratio=round(duration_seconds / max(static_duration_seconds, 1), 4),
            polyline=polyline,
        )

    @staticmethod
    def _waypoint(hospital: Hospital) -> dict[str, Any]:
        return {
            "location": {
                "latLng": {
                    "latitude": hospital.latitude,
                    "longitude": hospital.longitude,
                }
            }
        }

    @staticmethod
    def _parse_duration_seconds(value: str) -> float:
        if value.endswith("s"):
            return float(value[:-1])
        raise ValueError(f"Unexpected Google duration value: {value}")

    @staticmethod
    def decode_polyline(encoded: str) -> list[list[float]]:
        index = 0
        lat = 0
        lng = 0
        coordinates: list[list[float]] = []

        while index < len(encoded):
            result = 0
            shift = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            lat += ~(result >> 1) if result & 1 else result >> 1

            result = 0
            shift = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            lng += ~(result >> 1) if result & 1 else result >> 1

            coordinates.append([lat / 1e5, lng / 1e5])

        return coordinates
