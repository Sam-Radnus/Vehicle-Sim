from __future__ import annotations

import random
import string
import time

import aiohttp

from .base import PositionRecord


def _random_plate() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=7))


class WsWriter:
    """Sends position records to the pulse-live-location WebSocket endpoint."""

    def __init__(
        self,
        endpoint: str = "ws://localhost:8000/ws/set_current_location",
        timeout_s: float = 5.0,
    ) -> None:
        self._endpoint = endpoint
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
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
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        if self._ws is None or self._ws.closed:
            self._ws = await self._session.ws_connect(self._endpoint)

    async def write(self, record: PositionRecord) -> None:
        try:
            await self._ensure_connection()
        except (aiohttp.ClientError, OSError) as e:
            print(f"[ws_writer] connection error: {e}")
            return

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

        try:
            await self._ws.send_json(payload)  # type: ignore[union-attr]
            resp = await self._ws.receive_json()  # type: ignore[union-attr]
            if resp.get("status") != "ok":
                print(f"[ws_writer] server error: {resp}")
        except (aiohttp.ClientError, TypeError) as e:
            print(f"[ws_writer] send error: {e}")
            self._ws = None

    async def close(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
            self._ws = None
        if self._session is not None:
            await self._session.close()
            self._session = None
