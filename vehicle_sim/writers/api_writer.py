from __future__ import annotations

import asyncio
import logging
import random
import string
import time

import aiohttp

from .base import PositionRecord

logger = logging.getLogger(__name__)


def _random_plate() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=7))


class WsWriter:
    """Sends position records to the pulse-live-location WebSocket endpoint.

    Uses a single WebSocket connection with an asyncio.Lock to serialize
    send/receive pairs across concurrent vehicle tasks.
    """

    def __init__(
        self,
        endpoint: str = "ws://localhost:8000/ws/set_current_location",
    ) -> None:
        self._endpoint = endpoint
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._lock: asyncio.Lock | None = None
        self._sequence: dict[str, int] = {}
        self._vehicle_meta: dict[str, dict] = {}

    def _get_meta(self, vehicle_id: str) -> dict:
        if vehicle_id not in self._vehicle_meta:
            self._vehicle_meta[vehicle_id] = {
                "vehicle_id": vehicle_id,
                "number_plate": _random_plate(),
                "vehicle_name": f"Vehicle {vehicle_id[-8:]}",
                "driver_id": f"driver-{vehicle_id[-8:]}",
            }
        return self._vehicle_meta[vehicle_id]

    async def _ensure_connection(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        if self._ws is None or self._ws.closed:
            self._ws = await self._session.ws_connect(self._endpoint)

    async def write(self, record: PositionRecord) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()

        meta = self._get_meta(record.vehicle_id)
        seq = self._sequence.get(record.vehicle_id, 0)
        self._sequence[record.vehicle_id] = seq + 1

        ts_ms = int(record.timestamp * 1000)
        t = time.gmtime(record.timestamp)
        time_str = time.strftime("%H:%M:%S", t)

        payload = {
            "message_id": f"{record.vehicle_id}:{ts_ms}:{seq}",
            "lat": record.lat,
            "long": record.lon,
            "time": time_str,
            "driver_id": meta["driver_id"],
            "vehicle_info": {
                "vehicle_id": meta["vehicle_id"],
                "number_plate": meta["number_plate"],
                "vehicle_name": meta["vehicle_name"],
            },
        }

        async with self._lock:
            for attempt in range(3):
                try:
                    await self._ensure_connection()
                    await self._ws.send_json(payload)  # type: ignore[union-attr]
                    logger.info(
                        "[ws_writer] sent message_id=%s vehicle=%s plate=%s "
                        "driver=%s lat=%.6f long=%.6f time=%s",
                        payload["message_id"],
                        meta["vehicle_id"],
                        meta["number_plate"],
                        meta["driver_id"],
                        payload["lat"],
                        payload["long"],
                        payload["time"],
                    )
                    resp = await self._ws.receive_json()  # type: ignore[union-attr]
                    if resp.get("status") != "ok":
                        logger.error("[ws_writer] server error: %s", resp)
                    break
                except Exception as e:
                    self._ws = None
                    if attempt < 2:
                        logger.warning("[ws_writer] retry %d: %s", attempt + 1, e)
                        await asyncio.sleep(0.5)
                    else:
                        logger.error("[ws_writer] dropping message after 3 attempts: %s", e)

    async def close(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
            self._ws = None
        if self._session is not None:
            await self._session.close()
            self._session = None
