from __future__ import annotations

import unittest
from datetime import datetime

from app.data_store import HOSPITALS
from app.services.traffic_model_service import MODEL_FEATURES, TrafficModelService


class TrafficFeatureRowTests(unittest.TestCase):
    """Guard the time features handed to the trained traffic models.

    The models were trained on observations collected on the half hour, so the
    feature row has to stay on that grid. Only the time fields are exercised
    here; the joblib artifacts are gitignored and absent on a fresh clone, so
    nothing in this file may depend on them being loadable.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.service = TrafficModelService()
        cls.origin, cls.destination = HOSPITALS[0], HOSPITALS[1]

    def feature_row(self, when: datetime) -> dict:
        return self.service._build_feature_row(self.origin, self.destination, when)

    def test_minute_is_bucketed_onto_the_training_grid(self) -> None:
        for raw_minute, expected in [
            (0, 0), (1, 0), (17, 0), (29, 0),
            (30, 30), (31, 30), (47, 30), (59, 30),
        ]:
            with self.subTest(raw_minute=raw_minute):
                row = self.feature_row(datetime(2026, 8, 12, 9, raw_minute))
                self.assertEqual(row["minute"], expected)

    def test_minutes_in_the_same_half_hour_produce_identical_rows(self) -> None:
        # The prediction cache keys on the bucket, so two times in one bucket
        # must not disagree about their features.
        first = self.feature_row(datetime(2026, 8, 12, 9, 5))
        second = self.feature_row(datetime(2026, 8, 12, 9, 25))
        self.assertEqual(first, second)

    def test_crossing_the_half_hour_changes_the_row(self) -> None:
        before = self.feature_row(datetime(2026, 8, 12, 9, 29))
        after = self.feature_row(datetime(2026, 8, 12, 9, 31))
        self.assertNotEqual(before["minute"], after["minute"])

    def test_peak_night_and_weekend_flags_follow_the_clock(self) -> None:
        cases = [
            # (weekday date, hour, morning peak, evening peak, night, weekend)
            (datetime(2026, 8, 12, 8, 0), 1, 0, 0, 0),
            (datetime(2026, 8, 12, 17, 0), 0, 1, 0, 0),
            (datetime(2026, 8, 12, 23, 0), 0, 0, 1, 0),
            (datetime(2026, 8, 12, 3, 0), 0, 0, 1, 0),
            (datetime(2026, 8, 12, 12, 0), 0, 0, 0, 0),
            (datetime(2026, 8, 15, 12, 0), 0, 0, 0, 1),
        ]
        for when, morning, evening, night, weekend in cases:
            with self.subTest(when=when.isoformat()):
                row = self.feature_row(when)
                self.assertEqual(row["is_morning_peak"], morning)
                self.assertEqual(row["is_evening_peak"], evening)
                self.assertEqual(row["is_night"], night)
                self.assertEqual(row["is_weekend"], weekend)

    def test_row_covers_every_feature_the_models_expect(self) -> None:
        row = self.feature_row(datetime(2026, 8, 12, 9, 5))
        missing = [feature for feature in MODEL_FEATURES if feature not in row]
        self.assertEqual(missing, [], f"feature row is missing: {missing}")


if __name__ == "__main__":
    unittest.main()
