from __future__ import annotations

import aiohttp
import msgspec

from .base import PositionRecord, PositionWriter


class ApiWriter:
    """Sends position records to an HTTP API endpoint."""

    def __init__(
        self,
        endpoint: str = "http://localhost:8080/api/position",
        batch_size: int = 50,
        timeout_s: float = 5.0,
    ) -> None:
        self._endpoint = endpoint
        self._batch_size = batch_size
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._encoder = msgspec.json.Encoder()
        self._session: aiohttp.ClientSession | None = None
        self._buffer: list[PositionRecord] = []

    async def _ensure_session(self) -> None:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)

    async def _flush(self) -> None:
        if not self._buffer:
            return
        await self._ensure_session()
        payload = self._encoder.encode(self._buffer)
        try:
            async with self._session.post(  # type: ignore[union-attr]
                self._endpoint,
                data=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status >= 400:
                    print(f"[api_writer] POST failed: {resp.status}")
        except aiohttp.ClientError as e:
            print(f"[api_writer] request error: {e}")
        self._buffer.clear()

    async def write(self, record: PositionRecord) -> None:
        self._buffer.append(record)
        if len(self._buffer) >= self._batch_size:
            await self._flush()

    async def close(self) -> None:
        await self._flush()
        if self._session is not None:
            await self._session.close()
            self._session = None
