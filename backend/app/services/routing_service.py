from app.data_store import Hospital
from app.schemas import RouteOption
from app.services.google_routes_service import GoogleRoutesService
from app.services.osm_graph_routing_service import osm_graph_routing_service
from app.services.traffic_model_service import TrafficModelService


URGENCY_WEIGHTS = {
    "critical": {"time": 0.75, "risk": 0.20, "distance": 0.05},
    "high": {"time": 0.60, "risk": 0.30, "distance": 0.10},
    "moderate": {"time": 0.45, "risk": 0.40, "distance": 0.15},
}


class RoutingService:
    def __init__(self) -> None:
        self.traffic_model = TrafficModelService()
        self.google_routes = GoogleRoutesService()
        self.osm_graph = osm_graph_routing_service

    def compare_routes(self, origin: Hospital, destination: Hospital, urgency_class: str) -> list[RouteOption]:
        prediction = self.traffic_model.predict(origin, destination)
        baseline = self._estimate_route(origin, destination, urgency_class, "shortest_time", prediction)
        traffic_aware = self._estimate_route(origin, destination, urgency_class, "ml_traffic_risk_aware", prediction)
        return sorted([traffic_aware, baseline], key=lambda route: route.total_cost)

    def _estimate_route(
        self,
        origin: Hospital,
        destination: Hospital,
        urgency_class: str,
        strategy: str,
        prediction,
    ) -> RouteOption:
        distance_km = prediction.distance_km
        estimated_minutes = max(prediction.predicted_duration_seconds / 60, 1)
        polyline = [
            [origin.latitude, origin.longitude],
            [destination.latitude, destination.longitude],
        ]
        route_nodes: list[str] = []
        route_steps: list[dict] = []
        risk_features: dict = {}
        risk_factors: list[str] = []
        explanation: list[str] = []
        route_source = "cached_google_shaped_ml_features"

        graph_route = self.osm_graph.route(
            origin=origin,
            destination=destination,
            strategy=strategy,
            urgency_class=urgency_class,
            congestion_ratio=prediction.congestion_ratio,
        )
        google_route = (
            None
            if graph_route
            else self.google_routes.get_route(origin, destination, strategy)
        )

        if graph_route:
            distance_km = graph_route.distance_km
            estimated_minutes = graph_route.estimated_seconds / 60
            polyline = graph_route.polyline
            route_nodes = graph_route.node_ids
            route_steps = [
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
                for step in graph_route.route_steps
            ]
            risk_features = graph_route.risk_features
            risk_factors = graph_route.risk_factors
            explanation = graph_route.explanation
            route_source = "local_osm_graph_ml_weighted"
        elif google_route:
            distance_km = google_route.distance_km
            estimated_minutes = google_route.duration_seconds / 60
            polyline = google_route.polyline or polyline
            route_source = "live_google_routes_api"

        base_risk = prediction.risk_score

        if strategy == "shortest_time":
            risk_score = (
                min(graph_route.risk_score + 0.08, 1.0)
                if graph_route
                else min(base_risk + 0.12, 1.0)
            )
            adjusted_minutes = (
                max(graph_route.estimated_seconds / 60, 1)
                if graph_route
                else max(google_route.static_duration_seconds / 60, 1)
                if google_route
                else max(prediction.static_duration_seconds / 60, 1)
            )
        else:
            risk_score = graph_route.risk_score if graph_route else base_risk
            adjusted_minutes = estimated_minutes

        if not explanation:
            risk_factors = self._fallback_risk_factors(base_risk, prediction.congestion_ratio)
            explanation = [
                f"Distance {distance_km:.2f} km",
                f"Estimated travel time {adjusted_minutes:.1f} min",
                f"Risk score {risk_score:.2f}",
                *risk_factors,
            ]
            route_steps = [
                {
                    "start_index": 0,
                    "end_index": 1,
                    "road_name": "recommended corridor",
                    "maneuver": "depart",
                    "distance_meters": round(distance_km * 1000, 1),
                    "estimated_seconds": round(adjusted_minutes * 60, 1),
                    "average_risk": round(risk_score, 3),
                    "instruction": f"Depart toward {destination.name} for {distance_km:.1f} km",
                }
            ]
            risk_features = {
                "average_edge_risk": round(base_risk, 3),
                "high_risk_km": 0,
                "traffic_signal_count": None,
                "intersection_count": None,
                "step_count": len(route_steps),
                "node_count": len(route_nodes),
            }

        weights = URGENCY_WEIGHTS.get(urgency_class, URGENCY_WEIGHTS["high"])
        normalized_time = min(adjusted_minutes / 45, 1.0)
        normalized_distance = min(distance_km / 20, 1.0)
        total_cost = (
            weights["time"] * normalized_time
            + weights["risk"] * risk_score
            + weights["distance"] * normalized_distance
        )

        return RouteOption(
            strategy=strategy,
            estimated_minutes=round(adjusted_minutes, 1),
            distance_km=round(distance_km, 2),
            risk_score=round(risk_score, 2),
            total_cost=round(total_cost, 3),
            congestion_ratio=(
                google_route.congestion_ratio
                if google_route
                else prediction.congestion_ratio
            ),
            model_used=(
                "local_osm_graph+" + prediction.model_used
                if graph_route
                else "live_google_routes_api"
                if google_route
                else prediction.model_used
            ),
            route_source=route_source,
            route_nodes=route_nodes,
            route_steps=route_steps,
            risk_features=risk_features,
            risk_factors=risk_factors,
            explanation=explanation,
            polyline=polyline,
        )

    @staticmethod
    def _fallback_risk_factors(risk_score: float, congestion_ratio: float) -> list[str]:
        factors: list[str] = []
        if risk_score >= 0.7:
            factors.append("High predicted route risk from cached traffic/OSM features")
        elif risk_score >= 0.45:
            factors.append("Moderate predicted route risk from cached traffic/OSM features")
        else:
            factors.append("Low predicted route risk")
        if congestion_ratio >= 1.4:
            factors.append("Elevated congestion ratio")
        return factors
