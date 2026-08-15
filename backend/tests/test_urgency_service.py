from __future__ import annotations

import unittest

from app.schemas import UrgencyPredictionRequest
from app.services.urgency_service import UrgencyService


def request(**overrides) -> UrgencyPredictionRequest:
    """Build a request that carries no risk factors unless a test adds one."""
    payload = {
        "condition_type": "observation",
        "oxygen_saturation_band": "normal",
        "blood_pressure_band": "stable",
        "consciousness_level": "alert",
        "ventilator_required": False,
        "required_icu_type": "medical",
    }
    payload.update(overrides)
    return UrgencyPredictionRequest(**payload)


class UrgencyScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = UrgencyService()

    def test_benign_case_scores_the_baseline_and_says_why(self) -> None:
        result = self.service.predict(request())
        self.assertEqual(result.urgency_score, 0.2)
        self.assertEqual(result.urgency_class, "moderate")
        self.assertEqual(result.explanation, ["No severe risk factor selected"])

    def test_each_risk_factor_contributes_its_documented_weight(self) -> None:
        cases = [
            ({"condition_type": "cardiac"}, 0.35, "High-risk condition category"),
            ({"oxygen_saturation_band": "low"}, 0.4, "Low oxygen saturation"),
            ({"oxygen_saturation_band": "critical"}, 0.5, "Critical oxygen saturation"),
            ({"blood_pressure_band": "unstable"}, 0.35, "Unstable blood pressure"),
            ({"blood_pressure_band": "shock"}, 0.45, "Blood pressure indicates shock"),
            ({"consciousness_level": "reduced"}, 0.3, "Reduced consciousness"),
            ({"consciousness_level": "unconscious"}, 0.4, "Patient unconscious"),
            ({"ventilator_required": True}, 0.4, "Ventilator required"),
        ]
        for overrides, expected_score, expected_reason in cases:
            with self.subTest(**overrides):
                result = self.service.predict(request(**overrides))
                self.assertAlmostEqual(result.urgency_score, expected_score, places=2)
                self.assertIn(expected_reason, result.explanation)

    def test_condition_outside_the_high_risk_set_adds_nothing(self) -> None:
        result = self.service.predict(request(condition_type="orthopaedic"))
        self.assertEqual(result.urgency_score, 0.2)
        self.assertNotIn("High-risk condition category", result.explanation)

    def test_oxygen_and_blood_pressure_bands_do_not_stack_within_themselves(self) -> None:
        # "critical" must not also collect the "low" weight, and likewise for shock.
        critical = self.service.predict(request(oxygen_saturation_band="critical"))
        self.assertEqual(len(critical.explanation), 1)
        shock = self.service.predict(request(blood_pressure_band="shock"))
        self.assertEqual(len(shock.explanation), 1)


class UrgencyClassBoundaryTests(unittest.TestCase):
    """The class thresholds are what downstream dispatch weighting keys off."""

    def setUp(self) -> None:
        self.service = UrgencyService()

    def test_just_below_high_is_still_moderate(self) -> None:
        # 0.2 + 0.25 = 0.45
        result = self.service.predict(request(blood_pressure_band="shock"))
        self.assertEqual(result.urgency_class, "moderate")

    def test_exactly_the_high_threshold_is_high(self) -> None:
        # 0.2 + 0.3 = 0.5
        result = self.service.predict(request(oxygen_saturation_band="critical"))
        self.assertEqual(result.urgency_score, 0.5)
        self.assertEqual(result.urgency_class, "high")

    def test_just_below_critical_is_still_high(self) -> None:
        # 0.2 + 0.15 + 0.15 + 0.2 = 0.7
        result = self.service.predict(
            request(
                condition_type="cardiac",
                blood_pressure_band="unstable",
                ventilator_required=True,
            )
        )
        self.assertEqual(result.urgency_class, "high")

    def test_exactly_the_critical_threshold_is_critical(self) -> None:
        # 0.2 + 0.15 + 0.2 + 0.2 = 0.75
        result = self.service.predict(
            request(
                condition_type="cardiac",
                oxygen_saturation_band="low",
                consciousness_level="unconscious",
            )
        )
        self.assertEqual(result.urgency_score, 0.75)
        self.assertEqual(result.urgency_class, "critical")

    def test_worst_case_is_capped_at_one(self) -> None:
        # Raw total is 1.30, which must not escape the 0-1 range the API promises.
        result = self.service.predict(
            request(
                condition_type="trauma",
                oxygen_saturation_band="critical",
                blood_pressure_band="shock",
                consciousness_level="unconscious",
                ventilator_required=True,
            )
        )
        self.assertEqual(result.urgency_score, 1.0)
        self.assertEqual(result.urgency_class, "critical")
        self.assertEqual(len(result.explanation), 5)

    def test_score_never_leaves_the_unit_interval(self) -> None:
        bands = ["normal", "low", "critical"]
        pressures = ["stable", "unstable", "shock"]
        levels = ["alert", "reduced", "unconscious"]
        for band in bands:
            for pressure in pressures:
                for level in levels:
                    for ventilator in (False, True):
                        result = self.service.predict(
                            request(
                                condition_type="sepsis",
                                oxygen_saturation_band=band,
                                blood_pressure_band=pressure,
                                consciousness_level=level,
                                ventilator_required=ventilator,
                            )
                        )
                        self.assertGreaterEqual(result.urgency_score, 0.0)
                        self.assertLessEqual(result.urgency_score, 1.0)
                        self.assertIn(
                            result.urgency_class, {"moderate", "high", "critical"}
                        )


if __name__ == "__main__":
    unittest.main()
