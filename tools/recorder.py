from __future__ import annotations
import asyncio, json
from pathlib import Path
from datetime import datetime, timezone

class NDJSONRecorder:
    def __init__(self, base_dir: str | Path = "data/records"):
        self.base_dir = Path(base_dir)
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=10000)
        self._task: asyncio.Task | None = None
        self._fh = None
        self._hour_key: str | None = None
        self.total_written = 0

    async def start(self):
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
        if self._fh:
            self._fh.flush()
            self._fh.close()
            self._fh = None

    async def enqueue(self, obj):
        # obj can be dict/pydantic or a pre-serialized JSON string
        if isinstance(obj, str):
            line = obj
        else:
            try:
                line = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
            except Exception:
                line = str(obj)
        await self.queue.put(line)

    def _rollover_if_needed(self, now: datetime):
        key = now.strftime("%Y%m%d_%H")  # UTC hour bucket
        if key != self._hour_key or self._fh is None:
            if self._fh:
                self._fh.flush()
                self._fh.close()
            self._hour_key = key
            path = self.base_dir / f"{key}.ndjson"
