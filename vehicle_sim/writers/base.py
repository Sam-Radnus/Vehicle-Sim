from __future__ import annotations

from typing import Protocol, runtime_checkable

import msgspec


class PositionRecord(msgspec.Struct, frozen=True):
    vehicle_id: str
    timestamp: float
    lat: float
    lon: float
    speed_kmh: float
    heading: float
    progress: float  # 0.0 to 1.0


@runtime_checkable
class PositionWriter(Protocol):
    async def write(self, record: PositionRecord) -> None: ...
    async def close(self) -> None: ...
