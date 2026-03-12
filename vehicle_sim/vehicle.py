"""Vehicle model — simulates realistic movement along a road route."""

from __future__ import annotations

import enum
import random
import uuid

from .geo import position_along_route, route_distances


class DrivingState(enum.Enum):
    CRUISING = "cruising"
    ACCELERATING = "accelerating"
    BRAKING = "braking"
    STOPPED = "stopped"


class Vehicle:
    __slots__ = (
        "vehicle_id",
        "city",
        "waypoints",
        "_cum_dists",
        "total_dist_km",
        "target_speed_kmh",
        "speed_kmh",
        "distance_covered_km",
        "state",
        "_stop_remaining_s",
        "_next_stop_dist_km",
        "_accel_rate",
        "_brake_rate",
    )

    def __init__(
        self,
        waypoints: list[tuple[float, float]],
        total_dist_km: float,
        city: str = "",
        vehicle_id: str | None = None,
    ) -> None:
        self.vehicle_id = vehicle_id or f"v-{uuid.uuid4().hex[:8]}"
        self.city = city
        self.waypoints = waypoints
        self._cum_dists = route_distances(waypoints)
        self.total_dist_km = total_dist_km

        # Speed characteristics
        self.target_speed_kmh = random.uniform(30.0, 70.0)
        self.speed_kmh: float = 0.0
        self.distance_covered_km: float = 0.0

        # Driving state
        self.state = DrivingState.ACCELERATING
        self._stop_remaining_s: float = 0.0
        self._accel_rate = random.uniform(8.0, 15.0)
        self._brake_rate = random.uniform(10.0, 20.0)

        self._next_stop_dist_km = self._schedule_next_stop()

    def _schedule_next_stop(self) -> float:
        """Schedule a stop 0.3-3 km ahead (traffic light, stop sign, etc.)."""
        ahead = random.uniform(0.3, 3.0)
        return self.distance_covered_km + ahead

    def tick(self, dt_seconds: float) -> bool:
        """Advance the vehicle by dt_seconds. Returns True if still moving."""
        if self.distance_covered_km >= self.total_dist_km:
            self.speed_kmh = 0.0
            return False

        if self.state == DrivingState.STOPPED:
            self._stop_remaining_s -= dt_seconds
            if self._stop_remaining_s <= 0:
                self.state = DrivingState.ACCELERATING
                self._next_stop_dist_km = self._schedule_next_stop()
            self.speed_kmh = 0.0
            return True

        # Check if we should start braking for the next stop
        dist_to_stop = self._next_stop_dist_km - self.distance_covered_km
        braking_dist_km = (self.speed_kmh / 3.6) ** 2 / (2 * self._brake_rate / 3.6) / 1000 if self._brake_rate > 0 else 0

        if dist_to_stop <= max(0.02, braking_dist_km) and self.state != DrivingState.BRAKING:
            self.state = DrivingState.BRAKING

        if self.state == DrivingState.ACCELERATING:
            self.speed_kmh += self._accel_rate * dt_seconds
            jittered_target = self.target_speed_kmh + random.gauss(0, 3.0)
            if self.speed_kmh >= jittered_target:
                self.speed_kmh = jittered_target
                self.state = DrivingState.CRUISING

        elif self.state == DrivingState.CRUISING:
            self.speed_kmh += random.gauss(0, 1.5)
            self.speed_kmh = max(15.0, min(self.speed_kmh, self.target_speed_kmh + 15.0))

        elif self.state == DrivingState.BRAKING:
            self.speed_kmh -= self._brake_rate * dt_seconds
            if self.speed_kmh <= 0.5:
                self.speed_kmh = 0.0
                self.state = DrivingState.STOPPED
                self._stop_remaining_s = random.uniform(3.0, 30.0)
                return True

        self.speed_kmh = max(0.0, self.speed_kmh)
        dist_delta = (self.speed_kmh / 3600.0) * dt_seconds
        self.distance_covered_km += dist_delta

        if self.distance_covered_km >= self.total_dist_km:
            self.distance_covered_km = self.total_dist_km
            self.speed_kmh = 0.0
            return False

        return True

    @property
    def progress(self) -> float:
        if self.total_dist_km <= 0:
            return 1.0
        return min(1.0, self.distance_covered_km / self.total_dist_km)

    @property
    def current_position(self) -> tuple[float, float, float]:
        """Returns (lat, lon, heading)."""
        return position_along_route(self.waypoints, self._cum_dists, self.distance_covered_km)
