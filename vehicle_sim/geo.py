"""Geographic utilities for coordinate generation and movement interpolation."""

from __future__ import annotations

import math
import random

# Earth radius in km
R = 6371.0

# Rough bounding box for India (default region)
DEFAULT_LAT_RANGE = (8.0, 35.0)
DEFAULT_LON_RANGE = (68.0, 97.0)


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in km between two points."""
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees from point 1 to point 2."""
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlon = rlon2 - rlon1
    x = math.sin(dlon) * math.cos(rlat2)
    y = math.cos(rlat1) * math.sin(rlat2) - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    return math.degrees(math.atan2(x, y)) % 360


def destination_point(lat: float, lon: float, bearing_deg: float, dist_km: float) -> tuple[float, float]:
    """Given a start point, bearing, and distance, return the destination point."""
    rlat = math.radians(lat)
    rlon = math.radians(lon)
    rb = math.radians(bearing_deg)
    ad = dist_km / R

    nlat = math.asin(math.sin(rlat) * math.cos(ad) + math.cos(rlat) * math.sin(ad) * math.cos(rb))
    nlon = rlon + math.atan2(
        math.sin(rb) * math.sin(ad) * math.cos(rlat),
        math.cos(ad) - math.sin(rlat) * math.sin(nlat),
    )
    return math.degrees(nlat), math.degrees(nlon)


def interpolate(lat1: float, lon1: float, lat2: float, lon2: float, fraction: float) -> tuple[float, float]:
    """Interpolate along the great-circle path. fraction in [0, 1]."""
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = 2 * math.asin(
        math.sqrt(
            math.sin((rlat2 - rlat1) / 2) ** 2
            + math.cos(rlat1) * math.cos(rlat2) * math.sin((rlon2 - rlon1) / 2) ** 2
        )
    )
    if d < 1e-10:
        return lat1, lon1
    a = math.sin((1 - fraction) * d) / math.sin(d)
    b = math.sin(fraction * d) / math.sin(d)
    x = a * math.cos(rlat1) * math.cos(rlon1) + b * math.cos(rlat2) * math.cos(rlon2)
    y = a * math.cos(rlat1) * math.sin(rlon1) + b * math.cos(rlat2) * math.sin(rlon2)
    z = a * math.sin(rlat1) + b * math.sin(rlat2)
    return math.degrees(math.atan2(z, math.sqrt(x**2 + y**2))), math.degrees(math.atan2(y, x))


def generate_waypoints(
    src: tuple[float, float],
    dst: tuple[float, float],
    num_waypoints: int = 5,
    max_deviation_km: float = 15.0,
) -> list[tuple[float, float]]:
    """Generate intermediate waypoints between src and dst to create a curved route.

    Waypoints deviate laterally from the straight-line path, simulating
    real roads that curve and turn.
    """
    points = [src]
    direct_bearing = bearing(src[0], src[1], dst[0], dst[1])
    total_dist = haversine(src[0], src[1], dst[0], dst[1])

    for i in range(1, num_waypoints + 1):
        frac = i / (num_waypoints + 1)
        # Base point along the direct path
        base_lat, base_lon = interpolate(src[0], src[1], dst[0], dst[1], frac)

        # Deviate perpendicular to the direct bearing
        # Deviation decreases near start/end (bell curve shape)
        deviation_scale = math.sin(frac * math.pi)  # peaks at 0.5
        max_dev = min(max_deviation_km, total_dist * 0.15) * deviation_scale
        lateral_offset = random.gauss(0, max_dev / 2)
        lateral_offset = max(-max_dev, min(max_dev, lateral_offset))

        # Perpendicular bearing (90 degrees to the right or left)
        perp_bearing = (direct_bearing + 90) % 360
        wp_lat, wp_lon = destination_point(base_lat, base_lon, perp_bearing, lateral_offset)
        points.append((wp_lat, wp_lon))

    points.append(dst)
    return points


def route_distances(waypoints: list[tuple[float, float]]) -> list[float]:
    """Return cumulative distances along waypoints. First element is 0."""
    dists = [0.0]
    for i in range(1, len(waypoints)):
        seg = haversine(waypoints[i - 1][0], waypoints[i - 1][1], waypoints[i][0], waypoints[i][1])
        dists.append(dists[-1] + seg)
    return dists


def position_along_route(
    waypoints: list[tuple[float, float]],
    cum_dists: list[float],
    distance_km: float,
) -> tuple[float, float, float]:
    """Get (lat, lon, heading) at a given distance along the route."""
    total = cum_dists[-1]
    distance_km = max(0.0, min(distance_km, total))

    # Find which segment we're on
    for i in range(1, len(cum_dists)):
        if distance_km <= cum_dists[i]:
            seg_start = cum_dists[i - 1]
            seg_len = cum_dists[i] - seg_start
            if seg_len < 1e-10:
                frac = 0.0
            else:
                frac = (distance_km - seg_start) / seg_len
            lat, lon = interpolate(
                waypoints[i - 1][0], waypoints[i - 1][1],
                waypoints[i][0], waypoints[i][1],
                frac,
            )
            hdg = bearing(
                waypoints[i - 1][0], waypoints[i - 1][1],
                waypoints[i][0], waypoints[i][1],
            )
            return lat, lon, hdg

    # At the end
    return waypoints[-1][0], waypoints[-1][1], bearing(
        waypoints[-2][0], waypoints[-2][1], waypoints[-1][0], waypoints[-1][1]
    )


def random_route(
    min_dist_km: float = 50.0,
    max_dist_km: float = 150.0,
    lat_range: tuple[float, float] = DEFAULT_LAT_RANGE,
    lon_range: tuple[float, float] = DEFAULT_LON_RANGE,
) -> tuple[tuple[float, float], tuple[float, float], float]:
    """Generate a random (src, dst) pair within the given distance range.

    Returns ((src_lat, src_lon), (dst_lat, dst_lon), distance_km).
    """
    for _ in range(1000):
        src_lat = random.uniform(*lat_range)
        src_lon = random.uniform(*lon_range)
        brng = random.uniform(0, 360)
        dist = random.uniform(min_dist_km, max_dist_km)
        dst_lat, dst_lon = destination_point(src_lat, src_lon, brng, dist)
        if lat_range[0] <= dst_lat <= lat_range[1] and lon_range[0] <= dst_lon <= lon_range[1]:
            return (src_lat, src_lon), (dst_lat, dst_lon), dist
    return (src_lat, src_lon), (dst_lat, dst_lon), dist  # type: ignore[possibly-undefined]
