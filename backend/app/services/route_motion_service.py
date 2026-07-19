from __future__ import annotations

import math
from dataclasses import dataclass


EARTH_RADIUS_M = 6_371_000.0


def haversine_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1 = math.radians(first[0])
    lat2 = math.radians(second[0])
    delta_lat = math.radians(second[0] - first[0])
    delta_lon = math.radians(second[1] - first[1])
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(value), math.sqrt(max(1 - value, 0)))


def bearing_degrees(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1 = math.radians(first[0])
    lat2 = math.radians(second[0])
    delta_lon = math.radians(second[1] - first[1])
    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


@dataclass(frozen=True)
class RouteProjection:
    progress_m: float
    latitude: float
    longitude: float
    offset_m: float
    segment_index: int


@dataclass(frozen=True)
class RouteTrack:
    points: tuple[tuple[float, float], ...]
    cumulative_m: tuple[float, ...]
    total_m: float

    @classmethod
    def from_polyline(cls, polyline: list[list[float]] | list[tuple[float, float]]) -> "RouteTrack | None":
        points: list[tuple[float, float]] = []
        for raw_point in polyline:
            if len(raw_point) < 2:
                continue
            point = (float(raw_point[0]), float(raw_point[1]))
            if points and haversine_m(points[-1], point) < 0.25:
                continue
            points.append(point)
        if len(points) < 2:
            return None
        cumulative = [0.0]
        for index in range(1, len(points)):
            cumulative.append(cumulative[-1] + haversine_m(points[index - 1], points[index]))
        if cumulative[-1] < 1:
            return None
        return cls(tuple(points), tuple(cumulative), cumulative[-1])

    def position_at(self, progress_m: float) -> tuple[float, float]:
        bounded = max(0.0, min(progress_m, self.total_m))
        segment_index = self._segment_for_progress(bounded)
        start = self.points[segment_index]
        end = self.points[min(segment_index + 1, len(self.points) - 1)]
        segment_start = self.cumulative_m[segment_index]
        segment_length = max(self.cumulative_m[min(segment_index + 1, len(self.points) - 1)] - segment_start, 0.001)
        ratio = max(0.0, min((bounded - segment_start) / segment_length, 1.0))
        return (
            start[0] + (end[0] - start[0]) * ratio,
            start[1] + (end[1] - start[1]) * ratio,
        )

    def heading_at(self, progress_m: float, lookahead_m: float = 24.0) -> float:
        start = self.position_at(progress_m)
        end = self.position_at(min(progress_m + lookahead_m, self.total_m))
        if haversine_m(start, end) < 0.5:
            start = self.position_at(max(0.0, progress_m - lookahead_m))
        return bearing_degrees(start, end)

    def project(
        self,
        latitude: float,
        longitude: float,
        minimum_progress_m: float = 0.0,
    ) -> RouteProjection:
        origin_latitude = math.radians(latitude)
        meters_per_degree_lat = math.pi * EARTH_RADIUS_M / 180
        meters_per_degree_lon = meters_per_degree_lat * max(math.cos(origin_latitude), 0.01)
        best: RouteProjection | None = None
        for index in range(len(self.points) - 1):
            segment_end_progress = self.cumulative_m[index + 1]
            if segment_end_progress + 35 < minimum_progress_m:
                continue
            start = self.points[index]
            end = self.points[index + 1]
            start_x = (start[1] - longitude) * meters_per_degree_lon
            start_y = (start[0] - latitude) * meters_per_degree_lat
            end_x = (end[1] - longitude) * meters_per_degree_lon
            end_y = (end[0] - latitude) * meters_per_degree_lat
            delta_x = end_x - start_x
            delta_y = end_y - start_y
            length_squared = delta_x * delta_x + delta_y * delta_y
            ratio = 0.0 if length_squared < 0.001 else -(start_x * delta_x + start_y * delta_y) / length_squared
            ratio = max(0.0, min(ratio, 1.0))
            segment_start_progress = self.cumulative_m[index]
            segment_length = max(self.cumulative_m[index + 1] - segment_start_progress, 0.001)
            minimum_ratio = max(
                0.0,
                min((minimum_progress_m - segment_start_progress) / segment_length, 1.0),
            )
            ratio = max(ratio, minimum_ratio)
            projected_x = start_x + delta_x * ratio
            projected_y = start_y + delta_y * ratio
            offset = math.hypot(projected_x, projected_y)
            progress = segment_start_progress + (
                self.cumulative_m[index + 1] - self.cumulative_m[index]
            ) * ratio
            candidate = RouteProjection(
                progress_m=progress,
                latitude=start[0] + (end[0] - start[0]) * ratio,
                longitude=start[1] + (end[1] - start[1]) * ratio,
                offset_m=offset,
                segment_index=index,
            )
            if best is None or candidate.offset_m < best.offset_m:
                best = candidate
        if best is None:
            point = self.position_at(minimum_progress_m)
            return RouteProjection(minimum_progress_m, point[0], point[1], haversine_m((latitude, longitude), point), 0)
        return best

    def _segment_for_progress(self, progress_m: float) -> int:
        low = 0
        high = len(self.cumulative_m) - 1
        while low < high:
            middle = (low + high) // 2
            if self.cumulative_m[middle] < progress_m:
                low = middle + 1
            else:
                high = middle
        return max(0, min(low - 1, len(self.points) - 2))
