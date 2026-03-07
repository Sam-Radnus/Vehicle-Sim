from __future__ import annotations

import asyncio
import os
import time

import aiofiles
import aiofiles.os
import msgspec

from .base import PositionRecord, PositionWriter


class FileWriter:
    """Writes position records to rotating log files using msgspec for fast JSON encoding."""

    def __init__(
        self,
        log_dir: str = "logs",
        max_file_bytes: int = 10 * 1024 * 1024,  # 10 MB
    ) -> None:
        self._log_dir = log_dir
        self._max_bytes = max_file_bytes
        self._encoder = msgspec.json.Encoder()
        self._current_file: aiofiles.threadpool.text.AsyncTextIndirectIO | None = None
        self._current_path: str = ""
        self._current_size: int = 0
        self._file_index: int = 0
        self._lock = asyncio.Lock()

    async def _ensure_dir(self) -> None:
        os.makedirs(self._log_dir, exist_ok=True)

    def _next_path(self) -> str:
        self._file_index += 1
        ts = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join(self._log_dir, f"positions_{ts}_{self._file_index:04d}.jsonl")

    async def _rotate_if_needed(self) -> None:
        if self._current_file is None or self._current_size >= self._max_bytes:
            if self._current_file is not None:
                await self._current_file.close()
            await self._ensure_dir()
            self._current_path = self._next_path()
            self._current_file = await aiofiles.open(self._current_path, mode="a")
            self._current_size = 0

    async def write(self, record: PositionRecord) -> None:
        async with self._lock:
            await self._rotate_if_needed()
            line = self._encoder.encode(record)
            data = line + b"\n"
            await self._current_file.write(data.decode())  # type: ignore[union-attr]
            self._current_size += len(data)

    async def close(self) -> None:
        if self._current_file is not None:
            await self._current_file.close()
            self._current_file = None
