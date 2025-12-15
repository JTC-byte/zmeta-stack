from __future__ import annotations

"""Async NDJSON recorder with optional retention trimming."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog

from backend.app.config import settings

log = structlog.get_logger("zmeta.recorder")


class NDJSONRecorder:
    def __init__(self, base_dir: str | Path = "data/records", max_age_hours: float | None = None):
        self.base_dir = Path(base_dir)
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=10000)
        self._task: asyncio.Task | None = None
        self._fh = None
        self._hour_key: str | None = None
        self.total_written = 0
        self.dropped_total = 0
        self.max_age = max_age_hours if max_age_hours and max_age_hours > 0 else None

    async def start(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
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

    async def enqueue(self, obj: str | dict[str, object]) -> None:
        if isinstance(obj, str):
            line = obj
        else:
            try:
                line = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
            except Exception:
                line = str(obj)
        try:
            self.queue.put_nowait(line)
        except asyncio.QueueFull:
            self.dropped_total += 1
            log.warning(
                "recorder queue full; dropping entry",
                dropped=self.dropped_total,
            )
            return
        await asyncio.sleep(0)

    def _rollover_if_needed(self, now: datetime) -> None:
        key = now.strftime("%Y%m%d_%H")
        if key != self._hour_key or self._fh is None:
            if self._fh:
                self._fh.flush()
                self._fh.close()
            self._hour_key = key
            path = self.base_dir / f"{key}.ndjson"
            self._fh = path.open("a", encoding="utf-8", buffering=1)
        if self.max_age:
            self._prune_old_files(now)

    def _prune_old_files(self, now: datetime) -> None:
        cutoff = now - timedelta(hours=self.max_age)
        for path in self.base_dir.glob("*.ndjson"):
            try:
                if datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) < cutoff:
                    path.unlink()
                    log.info(
                        "Removed recorder file older than retention",
                        file=path.name,
                        retention_hours=self.max_age,
                    )
            except Exception:
                log.exception("Failed pruning recorder file", path=str(path))

    async def _run(self) -> None:
        while True:
            line = await self.queue.get()
            now = datetime.now(timezone.utc)
            self._rollover_if_needed(now)
            try:
                self._fh.write(line)
                if not line.endswith("\n"):
                    self._fh.write("\n")
                self.total_written += 1
            except Exception:
                pass
            finally:
                self.queue.task_done()


recorder = NDJSONRecorder(max_age_hours=settings.recorder_retention_hours)
