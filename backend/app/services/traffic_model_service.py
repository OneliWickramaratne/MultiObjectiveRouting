from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from pathlib import Path

import pandas as pd

from app.data_store import Hospital


MODEL_FEATURES = [
    "pair_id",
    "origin_hospital_id",
    "destination_hospital_id",
    "hour",
    "minute",
    "dayofweek_num",
    "is_weekend",
    "is_morning_peak",
    "is_evening_peak",
    "is_night",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "distanceMeters",
    "distance_km",
    "static_duration_seconds",
    "osm_intersection_count",
    "osm_signal_count",
    "osm_route_risk_score",
    "traffic_normal_interval_count",
    "traffic_slow_interval_count",
    "traffic_jam_interval_count",
    "road_mix_trunk",
    "road_mix_primary",
    "road_mix_secondary",
    "road_mix_tertiary_local",
    "intersections_per_km",
    "signals_per_km",
    "jam_interval_ratio",
    "slow_or_jam_ratio",
    "static_eta_over_distance",
    "hospital_pair_code",
    "traffic_band_code",
]


@dataclass(frozen=True)
class TrafficPrediction:
    distance_km: float
    static_duration_seconds: float
    predicted_duration_seconds: float
    congestion_ratio: float
    risk_score: float
    model_used: str


class TrafficModelService:
    """Predict route ETA/risk from cached Google-shaped observations and OSM features."""

    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[3]
        self.imported_root = self.project_root / "_incoming_hos_zip" / "HOS"
        self.model_path = self._first_existing_path(
            [
                self.project_root / "ml" / "artifacts" / "best_congestion_ratio_model.joblib",
                self.imported_root / "best_congestion_ratio_model.joblib",
                self.imported_root / "best_congestion_ratio_model (1).joblib",
            ]
        )
        self.duration_model_path = self._first_existing_path(
            [
                self.project_root / "ml" / "artifacts" / "best_duration_model.joblib",
                self.imported_root / "best_duration_model.joblib",
            ]
        )
        self.feature_data_path = self._first_existing_path(
            [
                self.project_root / "data" / "traffic_model_ready.csv",
                self.imported_root / "traffic_model_ready.csv",
            ]
        )

    @property
    def google_routes_enabled(self) -> bool:
        return bool(os.getenv("GOOGLE_MAPS_API_KEY"))

    @cached_property
    def feature_data(self) -> pd.DataFrame | None:
        if not self.feature_data_path:
            return None
        return pd.read_csv(self.feature_data_path)

    @cached_property
    def feature_lookup(self) -> dict[tuple[int, int, int, int], dict]:
        df = self.feature_data
        if df is None:
            return {}

        lookup: dict[tuple[int, int, int, int], dict] = {}
        sort_columns = ["origin_hospital_id", "destination_hospital_id", "hour", "minute"]
        for _, row in df.sort_values(sort_columns).iterrows():
            minute_bucket = 30 if int(row["minute"]) >= 30 else 0
            key = (
                int(row["origin_hospital_id"]),
                int(row["destination_hospital_id"]),
                int(row["hour"]),
                minute_bucket,
            )
            lookup.setdefault(key, row[MODEL_FEATURES].to_dict())
        return lookup

    @cached_property
    def pair_fallback_lookup(self) -> dict[tuple[int, int], dict]:
        df = self.feature_data
        if df is None:
            return {}
        lookup: dict[tuple[int, int], dict] = {}
        for _, row in df.iterrows():
            key = (int(row["origin_hospital_id"]), int(row["destination_hospital_id"]))
            lookup.setdefault(key, row[MODEL_FEATURES].to_dict())
        return lookup

    @cached_property
    def prediction_cache(self) -> dict[tuple[str, str, int, int, int], TrafficPrediction]:
        return {}

    @cached_property
    def congestion_model(self):
        if not self.model_path:
            return None
        try:
            import joblib

            return joblib.load(self.model_path)
        except Exception:
            return None

    @cached_property
    def duration_model(self):
        if not self.duration_model_path:
            return None
        try:
            import joblib

            return joblib.load(self.duration_model_path)
        except Exception:
            return None

    def predict(self, origin: Hospital, destination: Hospital, when: datetime | None = None) -> TrafficPrediction:
        when = when or datetime.now()
        minute_bucket = 30 if when.minute >= 30 else 0
        cache_key = (origin.id, destination.id, when.weekday(), when.hour, minute_bucket)
        cached = self.prediction_cache.get(cache_key)
        if cached:
            return cached

        features = self._build_feature_row(origin, destination, when)
        feature_df = pd.DataFrame([features], columns=MODEL_FEATURES)

        congestion_model = self.congestion_model
        duration_model = self.duration_model
        if congestion_model is not None:
            congestion_ratio = float(congestion_model.predict(feature_df)[0])
            if duration_model is not None:
                duration_seconds = float(duration_model.predict(feature_df)[0])
            else:
                duration_seconds = features["static_duration_seconds"] * congestion_ratio
            model_used = "trained_congestion_model"
        else:
            congestion_ratio = self._fallback_congestion_ratio(when)
            duration_seconds = features["static_duration_seconds"] * congestion_ratio
            model_used = "fallback_time_formula"

        raw_risk = float(features["osm_route_risk_score"])
        risk_score = min(raw_risk / 80, 1.0)
        prediction = TrafficPrediction(
            distance_km=round(float(features["distance_km"]), 3),
            static_duration_seconds=round(float(features["static_duration_seconds"]), 1),
            predicted_duration_seconds=round(max(duration_seconds, 60.0), 1),
            congestion_ratio=round(max(congestion_ratio, 0.1), 4),
            risk_score=round(risk_score, 3),
            model_used=model_used,
        )
        if len(self.prediction_cache) > 512:
            self.prediction_cache.clear()
        self.prediction_cache[cache_key] = prediction
        return prediction

    def _build_feature_row(self, origin: Hospital, destination: Hospital, when: datetime) -> dict[str, float | int]:
        template = self._lookup_pair_template(origin, destination, when)
        if template:
            row = dict(template)
        else:
            row = self._fallback_feature_row(origin, destination)

        hour = when.hour
        # Observations were collected on the half hour, so the trained models
        # only ever saw minute 0 or 30. Bucket the same way the pair template
        # lookup and the prediction cache key already do; feeding the raw
        # minute through would put the model off its training distribution.
        minute = 30 if when.minute >= 30 else 0
        dayofweek = when.weekday()
        row.update(
            {
                "origin_hospital_id": int(origin.id),
                "destination_hospital_id": int(destination.id),
                "hour": hour,
                "minute": minute,
                "dayofweek_num": dayofweek,
                "is_weekend": int(dayofweek >= 5),
                "is_morning_peak": int(7 <= hour <= 9),
                "is_evening_peak": int(16 <= hour <= 19),
                "is_night": int(hour >= 22 or hour <= 5),
                "hour_sin": math.sin(2 * math.pi * hour / 24),
                "hour_cos": math.cos(2 * math.pi * hour / 24),
                "dow_sin": math.sin(2 * math.pi * dayofweek / 7),
                "dow_cos": math.cos(2 * math.pi * dayofweek / 7),
            }
        )

        normal, slow, jam = self._traffic_interval_counts(hour)
        total_intervals = max(normal + slow + jam, 1)
        row.update(
            {
                "traffic_normal_interval_count": normal,
                "traffic_slow_interval_count": slow,
                "traffic_jam_interval_count": jam,
                "jam_interval_ratio": jam / total_intervals,
                "slow_or_jam_ratio": (slow + jam) / total_intervals,
                "traffic_band_code": self._traffic_band_code(normal, slow, jam),
            }
        )

        for feature in MODEL_FEATURES:
            row.setdefault(feature, 0)
        return {feature: row[feature] for feature in MODEL_FEATURES}

    def _lookup_pair_template(self, origin: Hospital, destination: Hospital, when: datetime) -> dict | None:
        minute_bucket = 30 if when.minute >= 30 else 0
        exact = self.feature_lookup.get(
            (int(origin.id), int(destination.id), when.hour, minute_bucket)
        )
        if exact:
            return dict(exact)
        fallback = self.pair_fallback_lookup.get((int(origin.id), int(destination.id)))
        return dict(fallback) if fallback else None

    def _fallback_feature_row(self, origin: Hospital, destination: Hospital) -> dict[str, float | int]:
        distance_km = self._haversine_km(origin.latitude, origin.longitude, destination.latitude, destination.longitude)
        distance_meters = distance_km * 1000
        static_duration_seconds = distance_meters / 8.33
        intersections = max(int(distance_km * 11), 1)
        signals = max(int(distance_km * 1.2), 0)
        risk = intersections * 0.45 + signals * 1.2 + destination.risk_modifier * 10
        return {
            "pair_id": int(origin.id) * 10 + int(destination.id),
            "distanceMeters": distance_meters,
            "distance_km": distance_km,
            "static_duration_seconds": static_duration_seconds,
            "osm_intersection_count": intersections,
            "osm_signal_count": signals,
            "osm_route_risk_score": risk,
            "road_mix_trunk": 0.08,
            "road_mix_primary": 0.35,
            "road_mix_secondary": 0.25,
            "road_mix_tertiary_local": 0.32,
            "intersections_per_km": intersections / max(distance_km, 0.1),
            "signals_per_km": signals / max(distance_km, 0.1),
            "static_eta_over_distance": static_duration_seconds / max(distance_km, 0.1),
            "hospital_pair_code": int(origin.id) * 10 + int(destination.id),
        }

    @staticmethod
    def _traffic_interval_counts(hour: int) -> tuple[int, int, int]:
        if 7 <= hour <= 9 or 16 <= hour <= 19:
            return 3, 4, 2
        if 22 <= hour or hour <= 5:
            return 8, 1, 0
        return 5, 3, 1

    @staticmethod
    def _traffic_band_code(normal: int, slow: int, jam: int) -> int:
        total = max(normal + slow + jam, 1)
        jam_ratio = jam / total
        slow_jam_ratio = (slow + jam) / total
        if jam_ratio >= 0.35:
            return 4
        if slow_jam_ratio >= 0.60:
            return 3
        if slow_jam_ratio >= 0.35:
            return 2
        if slow_jam_ratio > 0:
            return 1
        return 0

    @staticmethod
    def _fallback_congestion_ratio(when: datetime) -> float:
        if 7 <= when.hour <= 9 or 16 <= when.hour <= 19:
            return 1.45
        if when.hour >= 22 or when.hour <= 5:
            return 0.9
        return 1.15

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

    @staticmethod
    def _first_existing_path(paths: list[Path]) -> Path | None:
        return next((path for path in paths if path.exists()), None)
