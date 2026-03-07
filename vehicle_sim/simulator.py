"""Core simulation engine — runs all vehicles concurrently."""

from __future__ import annotations

import asyncio
import random
import time

from .geo import random_route
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

        # Simulate network drop — skip this ping entirely
        if random.random() < drop_probability:
            if not still_moving:
                break
            interval = random.uniform(ping_min, ping_max)
            # Occasionally a longer gap (network outage, tunnel, etc.)
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

        # Variable interval: normal jitter + occasional longer gaps
        interval = random.uniform(ping_min, ping_max)
        if random.random() < 0.08:
            # Network hiccup — 2x to 5x the max interval
            interval = random.uniform(ping_max * 2, ping_max * 5)
        await asyncio.sleep(interval)


async def simulate(
    n: int,
    writer: PositionWriter,
    min_dist_km: float = 50.0,
    max_dist_km: float = 150.0,
    ping_min: float = 1.0,
    ping_max: float = 5.0,
    drop_probability: float = 0.05,
) -> None:
    """Spawn n vehicles and run them concurrently."""
    vehicles: list[Vehicle] = []
    for _ in range(n):
        src, dst, dist = random_route(min_dist_km, max_dist_km)
        v = Vehicle(src=src, dst=dst, direct_dist_km=dist)
        vehicles.append(v)
        print(
            f"[init] {v.vehicle_id}: "
            f"{src[0]:.4f},{src[1]:.4f} -> {dst[0]:.4f},{dst[1]:.4f} "
            f"(route {v.total_dist_km:.1f} km, target {v.target_speed_kmh:.0f} km/h, "
            f"{len(v.waypoints)} waypoints)"
        )

    print(
        f"\n[sim] Starting {n} vehicles, "
        f"ping {ping_min}-{ping_max}s, "
        f"drop rate {drop_probability:.0%} ...\n"
    )

    tasks = [
        asyncio.create_task(run_vehicle(v, writer, ping_min, ping_max, drop_probability))
        for v in vehicles
    ]

    done_count = 0
    for coro in asyncio.as_completed(tasks):
        await coro
        done_count += 1
        if done_count % max(1, n // 10) == 0 or done_count == n:
            print(f"[sim] {done_count}/{n} vehicles completed")

    await writer.close()
    print("[sim] All vehicles finished. Writer closed.")
