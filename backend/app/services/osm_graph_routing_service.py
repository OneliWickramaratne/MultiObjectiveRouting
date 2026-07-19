from __future__ import annotations

import math
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np

from app.data_store import Hospital


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRAPH_PATH = PROJECT_ROOT / "data" / "osm" / "colombo_drive.graphml"

URGENCY_RISK_SECONDS = {
    "critical": 2.0,
    "high": 5.0,
    "moderate": 9.0,
}


@dataclass(frozen=True)
class OSMRouteStep:
    start_index: int
    end_index: int
    road_name: str
    maneuver: str
    distance_meters: float
    estimated_seconds: float
    average_risk: float
    instruction: str


@dataclass(frozen=True)
class OSMGraphRoute:
    node_ids: list[str]
    polyline: list[list[float]]
    distance_km: float
    estimated_seconds: float
    risk_score: float
    route_steps: list[OSMRouteStep]
    risk_features: dict
    risk_factors: list[str]
    explanation: list[str]


class OSMGraphRoutingService:
    """Optional local OSM road routing with a fail-open legacy fallback."""

    def __init__(self) -> None:
        configured_path = os.getenv("OSM_GRAPH_PATH")
        self.graph_path = Path(configured_path) if configured_path else DEFAULT_GRAPH_PATH
        self._graph: nx.DiGraph | None = None
        self._node_ids: np.ndarray | None = None
        self._latitudes: np.ndarray | None = None
        self._longitudes: np.ndarray | None = None
        self._route_cache: dict[tuple[str, str, str, str, float], OSMGraphRoute] = {}
        self._load_attempted = False
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return os.getenv("OSM_GRAPH_ROUTING", "1").strip().lower() not in {
            "0",
            "false",
            "off",
        }

    @property
    def available(self) -> bool:
        return self.enabled and self._load_graph()

    def warmup(self) -> None:
        if self.enabled:
            self._load_graph()

    def route(
        self,
        origin: Hospital,
        destination: Hospital,
        strategy: str,
        urgency_class: str,
        congestion_ratio: float,
    ) -> OSMGraphRoute | None:
        return self.route_coordinates(
            origin_latitude=origin.latitude,
            origin_longitude=origin.longitude,
            destination_latitude=destination.latitude,
            destination_longitude=destination.longitude,
            strategy=strategy,
            urgency_class=urgency_class,
            congestion_ratio=congestion_ratio,
            cache_key_prefix=f"hospital:{origin.id}:{destination.id}",
        )

    def route_coordinates(
        self,
        origin_latitude: float,
        origin_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
        strategy: str,
        urgency_class: str,
        congestion_ratio: float,
        cache_key_prefix: str | None = None,
    ) -> OSMGraphRoute | None:
        if not self.available or self._graph is None:
            return None

        try:
            coordinate_key = cache_key_prefix or (
                f"{origin_latitude:.5f}:{origin_longitude:.5f}:"
                f"{destination_latitude:.5f}:{destination_longitude:.5f}"
            )
            cache_key = (
                coordinate_key,
                "",
                strategy,
                urgency_class,
                round(congestion_ratio, 2),
            )
            cached = self._route_cache.get(cache_key)
            if cached:
                return cached

            origin_node = self._nearest_node(origin_latitude, origin_longitude)
            destination_node = self._nearest_node(destination_latitude, destination_longitude)
            risk_seconds = URGENCY_RISK_SECONDS.get(
                urgency_class,
                URGENCY_RISK_SECONDS["high"],
            )

            def edge_weight(_u: str, _v: str, data: dict) -> float:
                travel_seconds = self._edge_travel_seconds(data, congestion_ratio)
                if strategy == "shortest_time":
                    return travel_seconds
                distance_units = float(data.get("length", 0.0)) / 100
                return (
                    travel_seconds
                    + float(data.get("risk", 0.0)) * distance_units * risk_seconds
                )

            nodes = nx.astar_path(
                self._graph,
                origin_node,
                destination_node,
                heuristic=lambda _first, _second: 0.0,
                weight=edge_weight,
            )
            result = self._route_result(nodes, congestion_ratio)
            if len(self._route_cache) > 512:
                self._route_cache.clear()
            self._route_cache[cache_key] = result
            return result
        except (nx.NetworkXNoPath, nx.NodeNotFound, KeyError, TypeError, ValueError):
            return None

    def _load_graph(self) -> bool:
        if self._graph is not None:
            return True
        if self._load_attempted:
            return False

        with self._lock:
            if self._graph is not None:
                return True
            if self._load_attempted:
                return False
            self._load_attempted = True

            if not self.graph_path.exists():
                return False
            try:
                graph = nx.read_graphml(self.graph_path)
                if not graph.is_directed():
                    graph = graph.to_directed()
                self._graph = nx.DiGraph(graph)
                self._node_ids = np.array(list(self._graph.nodes), dtype=object)
                self._latitudes = np.array(
                    [float(self._graph.nodes[node]["y"]) for node in self._node_ids],
                    dtype=float,
                )
                self._longitudes = np.array(
                    [float(self._graph.nodes[node]["x"]) for node in self._node_ids],
                    dtype=float,
                )
                return len(self._node_ids) > 0
            except (OSError, nx.NetworkXError, KeyError, TypeError, ValueError):
                self._graph = None
                return False

    def _nearest_node(self, latitude: float, longitude: float) -> str:
        if self._node_ids is None or self._latitudes is None or self._longitudes is None:
            raise ValueError("OSM graph is not loaded")
        latitude_scale = math.cos(math.radians(latitude))
        distances = (
            (self._latitudes - latitude) ** 2
            + ((self._longitudes - longitude) * latitude_scale) ** 2
        )
        return str(self._node_ids[int(np.argmin(distances))])

    def _route_result(
        self,
        nodes: list[str],
        congestion_ratio: float,
    ) -> OSMGraphRoute:
        if self._graph is None:
            raise ValueError("OSM graph is not loaded")

        distance_meters = 0.0
        estimated_seconds = 0.0
        distance_weighted_risk = 0.0
        route_steps: list[OSMRouteStep] = []
        previous_bearing: float | None = None
        total_signals = 0
        total_intersections = 0
        total_high_risk_meters = 0.0
        total_primary_meters = 0.0
        total_residential_meters = 0.0
        for edge_index, (first, second) in enumerate(zip(nodes, nodes[1:])):
            edge = self._graph[first][second]
            edge_length = float(edge.get("length", 0.0))
            edge_risk = float(edge.get("risk", 0.0))
            edge_seconds = self._edge_travel_seconds(edge, congestion_ratio)
            highway = str(edge.get("highway", "")).lower()
            total_signals += self._numeric_edge_value(edge, ("traffic_signals", "signals", "signal_count"))
            total_intersections += self._numeric_edge_value(edge, ("intersections", "intersection_count", "junctions"))
            if edge_risk >= 1.0:
                total_high_risk_meters += edge_length
            if any(kind in highway for kind in ("primary", "trunk", "motorway")):
                total_primary_meters += edge_length
            if any(kind in highway for kind in ("residential", "living_street", "service")):
                total_residential_meters += edge_length
            first_node = self._graph.nodes[first]
            second_node = self._graph.nodes[second]
            current_bearing = self._bearing_degrees(
                float(first_node["y"]),
                float(first_node["x"]),
                float(second_node["y"]),
                float(second_node["x"]),
            )
            road_name = self._edge_road_name(edge)
            maneuver = "depart" if previous_bearing is None else self._maneuver(previous_bearing, current_bearing)
            step_index = len(route_steps)
            if (
                route_steps
                and route_steps[-1].road_name == road_name
                and maneuver == "continue"
            ):
                previous_step = route_steps[-1]
                combined_distance = previous_step.distance_meters + edge_length
                combined_seconds = previous_step.estimated_seconds + edge_seconds
                combined_risk = (
                    (previous_step.average_risk * previous_step.distance_meters + edge_risk * edge_length)
                    / max(combined_distance, 1.0)
                )
                route_steps[-1] = OSMRouteStep(
                    start_index=previous_step.start_index,
                    end_index=edge_index + 1,
                    road_name=previous_step.road_name,
                    maneuver=previous_step.maneuver,
                    distance_meters=round(combined_distance, 1),
                    estimated_seconds=round(combined_seconds, 1),
                    average_risk=round(combined_risk, 3),
                    instruction=self._instruction(previous_step.maneuver, previous_step.road_name, combined_distance),
                )
            else:
                route_steps.append(
                    OSMRouteStep(
                        start_index=edge_index,
                        end_index=edge_index + 1,
                        road_name=road_name,
                        maneuver=maneuver,
                        distance_meters=round(edge_length, 1),
                        estimated_seconds=round(edge_seconds, 1),
                        average_risk=round(edge_risk, 3),
                        instruction=self._instruction(maneuver, road_name, edge_length),
                    )
                )
            previous_bearing = current_bearing
            distance_meters += edge_length
            estimated_seconds += edge_seconds
            distance_weighted_risk += edge_risk * edge_length

        polyline = [
            [
                float(self._graph.nodes[node]["y"]),
                float(self._graph.nodes[node]["x"]),
            ]
            for node in nodes
        ]
        average_road_risk = distance_weighted_risk / max(distance_meters, 1.0)
        risk_score = round(min(average_road_risk / 1.5, 1.0), 3)
        risk_features = {
            "average_edge_risk": round(average_road_risk, 3),
            "high_risk_km": round(total_high_risk_meters / 1000, 3),
            "traffic_signal_count": int(total_signals),
            "intersection_count": int(total_intersections),
            "primary_road_km": round(total_primary_meters / 1000, 3),
            "residential_road_km": round(total_residential_meters / 1000, 3),
            "step_count": len(route_steps),
            "node_count": len(nodes),
        }
        risk_factors = self._risk_factors(risk_score, risk_features, congestion_ratio)
        return OSMGraphRoute(
            node_ids=[str(node) for node in nodes],
            polyline=polyline,
            distance_km=round(distance_meters / 1000, 3),
            estimated_seconds=round(max(estimated_seconds, 60.0), 1),
            risk_score=risk_score,
            route_steps=route_steps,
            risk_features=risk_features,
            risk_factors=risk_factors,
            explanation=self._route_explanation(distance_meters, estimated_seconds, risk_score, risk_factors),
        )

    @staticmethod
    def _edge_road_name(data: dict) -> str:
        raw_name = data.get("name") or data.get("road_name") or data.get("ref") or data.get("highway")
        if isinstance(raw_name, list):
            raw_name = raw_name[0] if raw_name else None
        if raw_name is None:
            return "current road"
        value = str(raw_name).strip().strip("[]'\"")
        return value or "current road"

    @staticmethod
    def _bearing_degrees(
        latitude_1: float,
        longitude_1: float,
        latitude_2: float,
        longitude_2: float,
    ) -> float:
        phi_1 = math.radians(latitude_1)
        phi_2 = math.radians(latitude_2)
        delta_lambda = math.radians(longitude_2 - longitude_1)
        y = math.sin(delta_lambda) * math.cos(phi_2)
        x = math.cos(phi_1) * math.sin(phi_2) - math.sin(phi_1) * math.cos(phi_2) * math.cos(delta_lambda)
        return (math.degrees(math.atan2(y, x)) + 360) % 360

    @staticmethod
    def _maneuver(previous_bearing: float, current_bearing: float) -> str:
        delta = ((current_bearing - previous_bearing + 540) % 360) - 180
        if delta <= -125:
            return "sharp_left"
        if delta < -35:
            return "left"
        if delta >= 125:
            return "sharp_right"
        if delta > 35:
            return "right"
        return "continue"

    @staticmethod
    def _instruction(maneuver: str, road_name: str, distance_meters: float) -> str:
        distance = f"{round(distance_meters)} m" if distance_meters < 1000 else f"{distance_meters / 1000:.1f} km"
        if maneuver == "depart":
            return f"Depart on {road_name} for {distance}"
        if maneuver == "continue":
            return f"Continue on {road_name} for {distance}"
        if maneuver == "left":
            return f"Turn left onto {road_name}, then continue for {distance}"
        if maneuver == "right":
            return f"Turn right onto {road_name}, then continue for {distance}"
        if maneuver == "sharp_left":
            return f"Make a sharp left onto {road_name}, then continue for {distance}"
        if maneuver == "sharp_right":
            return f"Make a sharp right onto {road_name}, then continue for {distance}"
        return f"Proceed on {road_name} for {distance}"

    @staticmethod
    def _numeric_edge_value(data: dict, keys: tuple[str, ...]) -> int:
        for key in keys:
            raw_value = data.get(key)
            if raw_value is None:
                continue
            try:
                return int(float(raw_value))
            except (TypeError, ValueError):
                continue
        return 0

    @staticmethod
    def _risk_factors(risk_score: float, risk_features: dict, congestion_ratio: float) -> list[str]:
        factors: list[str] = []
        if risk_score >= 0.7:
            factors.append("High average road-segment risk")
        elif risk_score >= 0.45:
            factors.append("Moderate road-segment risk")
        else:
            factors.append("Low road-segment risk")
        if risk_features["high_risk_km"] >= 1:
            factors.append(f"{risk_features['high_risk_km']} km on high-risk segments")
        if risk_features["traffic_signal_count"] >= 5:
            factors.append(f"{risk_features['traffic_signal_count']} traffic signals")
        if risk_features["intersection_count"] >= 10:
            factors.append(f"{risk_features['intersection_count']} intersections/junctions")
        if congestion_ratio >= 1.4:
            factors.append("Elevated congestion ratio")
        if risk_features["residential_road_km"] > risk_features["primary_road_km"]:
            factors.append("Uses more local/residential roads than primary corridors")
        if not factors:
            factors.append("No major risk feature detected")
        return factors

    @staticmethod
    def _route_explanation(distance_meters: float, estimated_seconds: float, risk_score: float, risk_factors: list[str]) -> list[str]:
        return [
            f"Distance {distance_meters / 1000:.2f} km",
            f"Estimated travel time {estimated_seconds / 60:.1f} min",
            f"Risk score {risk_score:.2f}",
            *risk_factors[:4],
        ]

    @staticmethod
    def _edge_travel_seconds(data: dict, congestion_ratio: float) -> float:
        length = float(data.get("length", 0.0))
        speed_kph = max(float(data.get("speed_kph", 30.0)), 5.0)
        return length / (speed_kph / 3.6) * max(congestion_ratio, 0.1)

    @staticmethod
    def _haversine_meters(
        latitude_1: float,
        longitude_1: float,
        latitude_2: float,
        longitude_2: float,
    ) -> float:
        radius = 6_371_000
        phi_1 = math.radians(latitude_1)
        phi_2 = math.radians(latitude_2)
        delta_phi = math.radians(latitude_2 - latitude_1)
        delta_lambda = math.radians(longitude_2 - longitude_1)
        value = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2) ** 2
        )
        return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


osm_graph_routing_service = OSMGraphRoutingService()
