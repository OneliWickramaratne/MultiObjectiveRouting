from __future__ import annotations

import unittest

from app.services.route_motion_service import RouteTrack


class RouteMotionTests(unittest.TestCase):
    def setUp(self) -> None:
        track = RouteTrack.from_polyline(
            [
                [6.9000, 79.8600],
                [6.9000, 79.8610],
                [6.9010, 79.8610],
            ]
        )
        self.assertIsNotNone(track)
        self.track = track

    def test_position_is_interpolated_by_distance(self) -> None:
        midpoint = self.track.position_at(self.track.cumulative_m[1] / 2)

        self.assertAlmostEqual(midpoint[0], 6.9000, places=7)
        self.assertAlmostEqual(midpoint[1], 79.8605, places=5)

    def test_projection_snaps_to_road_and_never_regresses(self) -> None:
        first_leg_end = self.track.cumulative_m[1]
        projection = self.track.project(
            6.90025,
            79.8604,
            minimum_progress_m=first_leg_end + 10,
        )

        self.assertGreaterEqual(projection.progress_m, first_leg_end + 10)
        self.assertAlmostEqual(projection.longitude, 79.8610, places=5)
        self.assertLess(projection.offset_m, 75)

    def test_heading_looks_ahead_along_the_active_segment(self) -> None:
        eastbound_heading = self.track.heading_at(10)
        northbound_heading = self.track.heading_at(self.track.cumulative_m[1] + 20)

        self.assertAlmostEqual(eastbound_heading, 90, delta=5)
        self.assertAlmostEqual(northbound_heading, 0, delta=5)


if __name__ == "__main__":
    unittest.main()
