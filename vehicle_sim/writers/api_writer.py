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

    Uses a single WebSocket connection with an asyncio queue to serialize
    all sends and avoid concurrent receive() issues.
    """

    def __init__(
        self,
        endpoint: str = "ws://localhost:8000/ws/set_current_location",
    ) -> None:
        self._endpoint = endpoint
        self._queue: asyncio.Queue[PositionRecord | None] = asyncio.Queue()
        self._sequence: dict[str, int] = {}
        self._vehicle_meta: dict[str, dict] = {}
        self._sender_task: asyncio.Task | None = None

    def _get_meta(self, vehicle_id: str) -> dict:
        if vehicle_id not in self._vehicle_meta:
            self._vehicle_meta[vehicle_id] = {
                "vehicle_id": vehicle_id,
                "number_plate": _random_plate(),
                "vehicle_name": f"Vehicle {vehicle_id[-8:]}",
                "driver_id": f"driver-{vehicle_id[-8:]}",
            }
        return self._vehicle_meta[vehicle_id]

    def _build_payload(self, record: PositionRecord) -> dict:
        meta = self._get_meta(record.vehicle_id)
        seq = self._sequence.get(record.vehicle_id, 0)
        self._sequence[record.vehicle_id] = seq + 1

        ts_ms = int(record.timestamp * 1000)
        t = time.gmtime(record.timestamp)
        time_str = time.strftime("%H:%M:%S", t)

        return {
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

    async def _sender_loop(self) -> None:
        """Single coroutine that owns the WebSocket connection."""
        session = aiohttp.ClientSession()
        ws: aiohttp.ClientWebSocketResponse | None = None

        try:
            while True:
                record = await self._queue.get()
                if record is None:
                    break

                payload = self._build_payload(record)
                meta = self._vehicle_meta[record.vehicle_id]

                for attempt in range(3):
                    try:
                        if ws is None or ws.closed:
                            ws = await session.ws_connect(self._endpoint)

                        await ws.send_json(payload)
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
                        resp = await ws.receive_json()
                        if resp.get("status") != "ok":
                            logger.error("[ws_writer] server error: %s", resp)
                        break
                    except Exception as e:
                        ws = None
                        if attempt < 2:
                            logger.warning("[ws_writer] retry %d: %s", attempt + 1, e)
                            await asyncio.sleep(0.5)
                        else:
                            logger.error("[ws_writer] dropping message after 3 attempts: %s", e)
        finally:
            if ws is not None and not ws.closed:
                await ws.close()
            await session.close()

    async def write(self, record: PositionRecord) -> None:
        if self._sender_task is None:
            self._sender_task = asyncio.create_task(self._sender_loop())
        await self._queue.put(record)

    async def close(self) -> None:
        if self._sender_task is not None:
            await self._queue.put(None)
            await self._sender_task
            self._sender_task = None
