"""Core simulation engine — runs all vehicles concurrently."""

from __future__ import annotations

import asyncio
import random
import time

import aiohttp

from .geo import CITIES, generate_city_route
from .vehicle import Vehicle
from .writers.base import PositionRecord, PositionWriter


async def run_vehicle(
    vehicle: Vehicle,
    writer: PositionWriter,
    ping_min: float = 1.0,
    ping_max: float = 5.0,
    drop_probability: float = 0.05,
) -> None:
    """Simulate a single vehicle with variable ping intervals and occasional drops."""
    last_ping = time.monotonic()

    while True:
        now = time.monotonic()
        dt = now - last_ping
        last_ping = now

        still_moving = vehicle.tick(dt)

        # Simulate network drop
        if random.random() < drop_probability:
            if not still_moving:
                break
            interval = random.uniform(ping_min, ping_max)
            if random.random() < 0.1:
                interval = random.uniform(ping_max, ping_max * 4)
            await asyncio.sleep(interval)
            continue

        lat, lon, heading = vehicle.current_position
        record = PositionRecord(
            vehicle_id=vehicle.vehicle_id,
            timestamp=time.time(),
            lat=round(lat, 6),
            lon=round(lon, 6),
            speed_kmh=round(vehicle.speed_kmh, 1),
            heading=round(heading, 1),
            progress=round(vehicle.progress, 4),
        )
        await writer.write(record)

        if not still_moving:
            break

        interval = random.uniform(ping_min, ping_max)
        if random.random() < 0.08:
            interval = random.uniform(ping_max * 2, ping_max * 5)
        await asyncio.sleep(interval)


async def _create_vehicle(
    session: aiohttp.ClientSession,
    city: str | None,
    semaphore: asyncio.Semaphore,
    radius_km: float | None = None,
) -> Vehicle:
    """Create a single vehicle with an OSRM road route."""
    async with semaphore:
        waypoints, dist_km, city_name = await generate_city_route(session, city, radius_km)
        v = Vehicle(waypoints=waypoints, total_dist_km=dist_km, city=city_name)
        print(
            f"[init] {v.vehicle_id} ({city_name}): "
            f"route {dist_km:.1f} km, {len(waypoints)} road points, "
            f"target {v.target_speed_kmh:.0f} km/h"
        )
        return v


async def _create_and_run_vehicle(
    session: aiohttp.ClientSession,
    city: str | None,
    semaphore: asyncio.Semaphore,
    writer: PositionWriter,
    ping_min: float,
    ping_max: float,
    drop_probability: float,
    radius_km: float | None = None,
) -> None:
    """Create a vehicle and immediately start its simulation."""
    vehicle = await _create_vehicle(session, city, semaphore, radius_km)
    await run_vehicle(vehicle, writer, ping_min, ping_max, drop_probability)


async def simulate(
    n: int,
    writer: PositionWriter,
    ping_min: float = 1.0,
    ping_max: float = 5.0,
    drop_probability: float = 0.05,
    city: str | None = None,
    radius_km: float | None = None,
) -> None:
    """Spawn n vehicles and run them concurrently."""
    print(f"[init] Fetching road routes for {n} vehicles from OSRM...")
    radius_label = f", radius {radius_km} km" if radius_km else ""
    print(
        f"[sim] Vehicles start moving as soon as their route is ready, "
        f"ping {ping_min}-{ping_max}s, "
        f"drop rate {drop_probability:.0%}{radius_label}\n"
    )

    # Rate-limit OSRM requests (max 5 concurrent)
    semaphore = asyncio.Semaphore(5)

    async with aiohttp.ClientSession() as session:
        run_tasks = [
            asyncio.create_task(
                _create_and_run_vehicle(
                    session, city, semaphore, writer,
                    ping_min, ping_max, drop_probability, radius_km,
                )
            )
            for _ in range(n)
        ]

        done_count = 0
        for coro in asyncio.as_completed(run_tasks):
            await coro
            done_count += 1
            if done_count % max(1, n // 10) == 0 or done_count == n:
                print(f"[sim] {done_count}/{n} vehicles completed")

    await writer.close()
    print("[sim] All vehicles finished. Writer closed.")
