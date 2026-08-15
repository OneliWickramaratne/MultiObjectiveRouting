from __future__ import annotations

import unittest

from app.data_store import HOSPITALS
from app.services.routing_service import URGENCY_WEIGHTS, RoutingService
from app.services.traffic_model_service import TrafficPrediction


class StubTrafficModel:
    def __init__(self, prediction: TrafficPrediction) -> None:
        self.prediction = prediction

    def predict(self, origin, destination, when=None) -> TrafficPrediction:
        return self.prediction


class StubUnavailable:
    """Stands in for the OSM graph and Google client when neither can answer."""

    def route(self, **kwargs):
        return None

    def get_route(self, *args, **kwargs):
        return None


def prediction(risk_score: float = 0.5, congestion_ratio: float = 1.2) -> TrafficPrediction:
    return TrafficPrediction(
        distance_km=10.0,
        static_duration_seconds=900.0,
        predicted_duration_seconds=1200.0,
        congestion_ratio=congestion_ratio,
        risk_score=risk_score,
        model_used="stub_model",
    )


def routing_service(pred: TrafficPrediction | None = None) -> RoutingService:
    """A RoutingService with both route providers stubbed out.

    Forcing the graph and Google lookups to return nothing pins the run to the
    deterministic prediction-only path, so these tests neither load the
    gitignored joblib artifacts nor reach the network.
    """
    service = RoutingService()
    service.traffic_model = StubTrafficModel(pred or prediction())
    service.osm_graph = StubUnavailable()
    service.google_routes = StubUnavailable()
    return service


class UrgencyWeightTests(unittest.TestCase):
    def test_every_profile_is_a_full_allocation(self) -> None:
        for urgency_class, weights in URGENCY_WEIGHTS.items():
            with self.subTest(urgency_class=urgency_class):
                self.assertAlmostEqual(sum(weights.values()), 1.0, places=9)

    def test_urgency_shifts_emphasis_from_risk_onto_time(self) -> None:
        # The central design claim: the more urgent the case, the more the
        # ranking cares about arriving quickly relative to avoiding risk.
        order = ["moderate", "high", "critical"]
        times = [URGENCY_WEIGHTS[c]["time"] for c in order]
        risks = [URGENCY_WEIGHTS[c]["risk"] for c in order]
        self.assertEqual(times, sorted(times))
        self.assertEqual(risks, sorted(risks, reverse=True))


class FallbackRiskFactorTests(unittest.TestCase):
    def factors(self, risk: float, congestion: float = 1.0) -> list[str]:
        return RoutingService._fallback_risk_factors(risk, congestion)

    def test_risk_bands_are_reported_at_their_boundaries(self) -> None:
        cases = [
            (0.0, "Low predicted route risk"),
            (0.44, "Low predicted route risk"),
            (0.45, "Moderate predicted route risk from cached traffic/OSM features"),
            (0.69, "Moderate predicted route risk from cached traffic/OSM features"),
            (0.70, "High predicted route risk from cached traffic/OSM features"),
            (1.0, "High predicted route risk from cached traffic/OSM features"),
        ]
        for risk, expected in cases:
            with self.subTest(risk=risk):
                self.assertEqual(self.factors(risk)[0], expected)

    def test_congestion_is_called_out_only_once_it_is_elevated(self) -> None:
        self.assertNotIn("Elevated congestion ratio", self.factors(0.5, congestion=1.39))
        self.assertIn("Elevated congestion ratio", self.factors(0.5, congestion=1.4))


class CompareRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.origin, self.destination = HOSPITALS[0], HOSPITALS[1]

    def compare(self, urgency: str = "critical", pred: TrafficPrediction | None = None):
        return routing_service(pred).compare_routes(self.origin, self.destination, urgency)

    def test_both_strategies_are_offered(self) -> None:
        options = self.compare()
        self.assertEqual(len(options), 2)
        self.assertEqual(
            {option.strategy for option in options},
            {"shortest_time", "ml_traffic_risk_aware"},
        )

    def test_options_are_ordered_by_total_cost(self) -> None:
        for urgency in ["critical", "high", "moderate"]:
            with self.subTest(urgency=urgency):
                options = self.compare(urgency)
                costs = [option.total_cost for option in options]
                self.assertEqual(costs, sorted(costs))

    def test_the_time_first_route_is_scored_as_the_riskier_one(self) -> None:
        # This is the tradeoff the evaluation reports: going fastest costs risk.
        options = {option.strategy: option for option in self.compare()}
        self.assertGreater(
            options["shortest_time"].risk_score,
            options["ml_traffic_risk_aware"].risk_score,
        )

    def test_risk_score_stays_within_range_even_when_already_maximal(self) -> None:
        options = {o.strategy: o for o in self.compare(pred=prediction(risk_score=1.0))}
        for strategy, option in options.items():
            with self.subTest(strategy=strategy):
                self.assertLessEqual(option.risk_score, 1.0)

    def test_an_unknown_urgency_class_is_scored_as_high(self) -> None:
        unknown = self.compare("not-a-class")
        known = self.compare("high")
        self.assertEqual(
            [o.total_cost for o in unknown],
            [o.total_cost for o in known],
        )

    def test_a_more_urgent_case_never_scores_a_route_as_costlier_on_risk_alone(self) -> None:
        # With time and distance fixed by the stub, dropping the risk weight
        # must not make a risky route look worse to a critical case.
        risky = prediction(risk_score=0.9)
        critical = {o.strategy: o for o in self.compare("critical", risky)}
        moderate = {o.strategy: o for o in self.compare("moderate", risky)}
        for strategy in critical:
            with self.subTest(strategy=strategy):
                self.assertLess(critical[strategy].total_cost, moderate[strategy].total_cost)

    def test_explanation_and_steps_are_populated_on_the_fallback_path(self) -> None:
        option = self.compare()[0]
        self.assertTrue(option.explanation)
        self.assertEqual(len(option.route_steps), 1)
        self.assertTrue(option.risk_factors)
        self.assertEqual(len(option.polyline), 2)


if __name__ == "__main__":
    unittest.main()
