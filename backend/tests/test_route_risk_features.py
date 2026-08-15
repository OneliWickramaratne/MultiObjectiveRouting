from __future__ import annotations

import unittest

import networkx as nx
import numpy as np

from app.services.capacity_forecast_service import CapacityForecastService, HospitalCapacityForecast
from app.services.osm_graph_routing_service import OSMGraphRoutingService
from app.services.simulation_analytics_service import SimulationAnalyticsService


def build_routing_service() -> OSMGraphRoutingService:
    """A corridor a->b->c->d, where `c` also spurs off to make it a junction."""
    graph = nx.DiGraph()
    points = {
        "a": (6.900, 79.860),
        "b": (6.905, 79.860),
        "c": (6.910, 79.860),
        "d": (6.915, 79.860),
        "spur1": (6.910, 79.870),
        "spur2": (6.910, 79.850),
    }
    for node, (latitude, longitude) in points.items():
        graph.add_node(
            node,
            y=latitude,
            x=longitude,
            highway="traffic_signals" if node in {"b", "c"} else "",
        )
    for first, second in [("a", "b"), ("b", "c"), ("c", "d"), ("c", "spur1"), ("c", "spur2")]:
        graph.add_edge(
            first,
            second,
            length=550.0,
            speed_kph=40.0,
            risk=0.5,
            highway="primary",
            name="Galle Road",
        )

    service = OSMGraphRoutingService()
    service._graph = graph
    service._load_attempted = True
    service._node_ids = np.array(list(graph.nodes), dtype=object)
    service._latitudes = np.array([points[n][0] for n in graph.nodes], dtype=float)
    service._longitudes = np.array([points[n][1] for n in graph.nodes], dtype=float)
    service._max_speed_mps = 40 / 3.6
    return service


class RouteRiskFeatureTests(unittest.TestCase):
    """The signal and junction counters used to read edge attributes that the
    Colombo graph does not define, so both were reported as 0 on every route."""

    def setUp(self) -> None:
        self.service = build_routing_service()

    def test_signals_and_junctions_are_counted_from_nodes(self) -> None:
        route = self.service.route_coordinates(
            6.900, 79.860, 6.915, 79.860, "shortest_time", "high", 1.0
        )

        self.assertEqual(route.risk_features["traffic_signal_count"], 2)
        self.assertEqual(route.risk_features["intersection_count"], 1)

    def test_edge_supplied_counters_take_priority(self) -> None:
        for _first, _second, data in self.service._graph.edges(data=True):
            data["traffic_signals"] = 2

        route = self.service.route_coordinates(
            6.900, 79.860, 6.915, 79.860, "shortest_time", "high", 1.0
        )

        self.assertEqual(route.risk_features["traffic_signal_count"], 6)

    def test_short_route_eta_agrees_with_its_explanation(self) -> None:
        self.service._graph["a"]["b"]["length"] = 20.0

        route = self.service.route_coordinates(
            6.900, 79.860, 6.905, 79.860, "shortest_time", "high", 1.0
        )

        self.assertEqual(route.estimated_seconds, 60.0)
        self.assertIn("1.0 min", route.explanation[1])


class AStarHeuristicTests(unittest.TestCase):
    """The heuristic was a constant 0.0, which silently degraded A* to Dijkstra."""

    def test_heuristic_never_overestimates_remaining_cost(self) -> None:
        service = build_routing_service()
        graph = service._graph

        for strategy in ("shortest_time", "ml_traffic_risk_aware"):
            for congestion in (0.5, 1.0, 1.8):
                with self.subTest(strategy=strategy, congestion=congestion):

                    def weight(_u, _v, data, strategy=strategy, congestion=congestion):
                        seconds = OSMGraphRoutingService._edge_travel_seconds(data, congestion)
                        if strategy == "shortest_time":
                            return seconds
                        return seconds + float(data["risk"]) * (float(data["length"]) / 100) * 5.0

                    def cost(path):
                        return sum(weight(u, v, graph[u][v]) for u, v in zip(path, path[1:]))

                    optimal = nx.dijkstra_path(graph, "a", "d", weight=weight)
                    found = nx.astar_path(
                        graph,
                        "a",
                        "d",
                        heuristic=service._time_heuristic("d", congestion),
                        weight=weight,
                    )

                    self.assertAlmostEqual(cost(found), cost(optimal), places=6)

    def test_missing_graph_file_fails_open(self) -> None:
        service = OSMGraphRoutingService()
        service.graph_path = service.graph_path.with_name("does-not-exist.graphml")

        route = service.route_coordinates(6.9, 79.8, 6.95, 79.9, "shortest_time", "high", 1.0)

        self.assertIsNone(route)
        self.assertIsNone(service._graph)
        self.assertIsNone(service._node_ids)


class CapacityForecastFallbackTests(unittest.TestCase):
    """A hospital with no per-bed rows reported zero availability, i.e. 100% full."""

    def test_hospital_without_bed_rows_uses_its_counters(self) -> None:
        class Hospital:
            id, name, total_beds, occupied_beds = "1", "H1", 20, 18

        class EmptyQuery:
            def filter(self, *args):
                return self

            def all(self):
                return []

            def count(self):
                return 0

        class FakeSession:
            def query(self, *args):
                return EmptyQuery()

        forecast = CapacityForecastService().forecast_hospital(FakeSession(), Hospital())

        self.assertEqual(forecast.current_available_beds, 2)
        self.assertEqual(forecast.current_occupied_beds, 18)
        self.assertTrue(all(point.pressure_level != "critical" for point in forecast.points))


class ScenarioArrivalSplitTests(unittest.TestCase):
    """Rounding pushed the final hospital's remainder negative, which subtracted
    a negative arrival count and handed it phantom beds."""

    def test_no_hospital_receives_negative_arrivals(self) -> None:
        forecasts = [
            HospitalCapacityForecast(str(i), f"H{i}", 2, 1, 1, 0, 0.5, 0.0, [], "")
            for i in range(1, 10)
        ]

        impacts = SimulationAnalyticsService()._hospital_impacts(
            forecasts=forecasts,
            total_arrivals=5,
            duration_hours=6,
            scenario="mass_casualty",
        )

        self.assertTrue(all(impact["projected_arrivals"] >= 0 for impact in impacts))
        self.assertTrue(all(impact["predicted_available_beds"] <= 2 for impact in impacts))


if __name__ == "__main__":
    unittest.main()
