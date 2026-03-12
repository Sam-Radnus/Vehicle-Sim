"""Geographic utilities — city definitions, OSRM routing, and movement math."""

from __future__ import annotations

import math
import random

import aiohttp

R = 6371.0

# --- Cities with bounding boxes (lat_min, lat_max, lon_min, lon_max) ---

CITIES: dict[str, tuple[float, float, float, float]] = {
    "san_francisco": (37.7050, 37.8120, -122.5150, -122.3550),
    "new_york":      (40.6950, 40.8200, -74.0200, -73.9100),
    "seattle":       (47.5010, 47.7340, -122.4360, -122.2360),
    "los_angeles":   (33.9000, 34.1000, -118.4000, -118.1500),
    "chicago":       (41.8000, 41.9500, -87.7500, -87.6000),
    "austin":        (30.2200, 30.3500, -97.8000, -97.6800),
    "boston":         (42.3300, 42.3950, -71.1200, -71.0200),
    "denver":        (39.6800, 39.7800, -105.0200, -104.9000),
}

OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlon = rlon2 - rlon1
    x = math.sin(dlon) * math.cos(rlat2)
    y = math.cos(rlat1) * math.sin(rlat2) - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    return math.degrees(math.atan2(x, y)) % 360


def interpolate(lat1: float, lon1: float, lat2: float, lon2: float, fraction: float) -> tuple[float, float]:
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


def route_distances(waypoints: list[tuple[float, float]]) -> list[float]:
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

    for i in range(1, len(cum_dists)):
        if distance_km <= cum_dists[i]:
            seg_start = cum_dists[i - 1]
            seg_len = cum_dists[i] - seg_start
            frac = 0.0 if seg_len < 1e-10 else (distance_km - seg_start) / seg_len
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

    return waypoints[-1][0], waypoints[-1][1], bearing(
        waypoints[-2][0], waypoints[-2][1], waypoints[-1][0], waypoints[-1][1]
    )


def city_center(city: str) -> tuple[float, float]:
    """Return the (lat, lon) center of a city's bounding box."""
    lat_min, lat_max, lon_min, lon_max = CITIES[city]
    return ((lat_min + lat_max) / 2, (lon_min + lon_max) / 2)


def random_point_in_radius(center: tuple[float, float], radius_km: float) -> tuple[float, float]:
    """Random (lat, lon) within *radius_km* of *center*."""
    # Random distance with uniform area distribution
    dist = radius_km * math.sqrt(random.random())
    angle = random.uniform(0, 2 * math.pi)
    # Approximate offset in degrees
    dlat = (dist * math.cos(angle)) / R * (180 / math.pi)
    dlon = (dist * math.sin(angle)) / (R * math.cos(math.radians(center[0]))) * (180 / math.pi)
    return (center[0] + dlat, center[1] + dlon)


def random_point_in_city(city: str, radius_km: float | None = None) -> tuple[float, float]:
    """Random (lat, lon) within a city's bounding box, or within *radius_km* of center."""
    if radius_km is not None:
        return random_point_in_radius(city_center(city), radius_km)
    lat_min, lat_max, lon_min, lon_max = CITIES[city]
    return (random.uniform(lat_min, lat_max), random.uniform(lon_min, lon_max))


def simplify_waypoints(waypoints: list[tuple[float, float]], max_points: int = 200) -> list[tuple[float, float]]:
    """Downsample waypoints if OSRM returns too many, keeping first and last."""
    if len(waypoints) <= max_points:
        return waypoints
    step = (len(waypoints) - 1) / (max_points - 1)
    indices = [round(i * step) for i in range(max_points)]
    return [waypoints[i] for i in indices]


async def fetch_osrm_route(
    session: aiohttp.ClientSession,
    src: tuple[float, float],
    dst: tuple[float, float],
) -> list[tuple[float, float]] | None:
    """Fetch a road route from OSRM. Returns list of (lat, lon) waypoints or None on failure."""
    # OSRM uses lon,lat order
    coords = f"{src[1]},{src[0]};{dst[1]},{dst[0]}"
    url = f"{OSRM_BASE}/{coords}?overview=full&geometries=geojson"

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                return None
            # GeoJSON coordinates are [lon, lat]
            coords_list = data["routes"][0]["geometry"]["coordinates"]
            # Convert to (lat, lon)
            waypoints = [(c[1], c[0]) for c in coords_list]
            return simplify_waypoints(waypoints)
    except Exception as e:
        print(f"[osrm] Route fetch failed: {e}")
        return None


async def generate_city_route(
    session: aiohttp.ClientSession,
    city: str | None = None,
    radius_km: float | None = None,
) -> tuple[list[tuple[float, float]], float, str]:
    """Generate a route within a random (or specified) city using OSRM.

    Returns (waypoints, route_distance_km, city_name).
    Retries with different random points if OSRM can't find a route.
    """
    if city is None:
        city = random.choice(list(CITIES.keys()))

    for _ in range(5):
        src = random_point_in_city(city, radius_km)
        dst = random_point_in_city(city, radius_km)

        # Ensure src and dst are at least 1km apart
        if haversine(src[0], src[1], dst[0], dst[1]) < 1.0:
            continue

        waypoints = await fetch_osrm_route(session, src, dst)
        if waypoints and len(waypoints) >= 2:
            dists = route_distances(waypoints)
            total_km = dists[-1]
            if total_km > 0.5:  # Skip trivially short routes
                return waypoints, total_km, city

    # Fallback: should rarely happen
    raise RuntimeError(f"Failed to generate route in {city} after retries")
