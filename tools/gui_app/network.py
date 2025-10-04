from __future__ import annotations

"""Async networking helpers for the GUI."""

import asyncio
import contextlib
import threading
from typing import Any, Callable, Coroutine

from websockets.client import connect as ws_connect
from websockets.exceptions import WebSocketException


class AsyncLoopThread:
    """Run a dedicated asyncio loop in a background thread."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def create_task(self, coro: Coroutine[Any, Any, Any]) -> None:
        def _schedule() -> None:
            self.loop.create_task(coro)

        self.loop.call_soon_threadsafe(_schedule)

    def stop(self) -> None:
        async def _shutdown() -> None:
            tasks = [t for t in asyncio.all_tasks(self.loop) if not t.done()]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        fut = asyncio.run_coroutine_threadsafe(_shutdown(), self.loop)
        with contextlib.suppress(Exception):
            fut.result(timeout=1.0)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=1.0)
        self.loop.close()


class WebSocketClient:
    """Minimal WebSocket consumer with auto-reconnect capability."""

    def __init__(
        self,
        loop_thread: AsyncLoopThread,
        url_factory: Callable[[], str],
        emitter: Callable[[str, Any], None],
    ) -> None:
        self.loop_thread = loop_thread
        self.loop = loop_thread.loop
        self.url_factory = url_factory
        self._emit = emitter
        self._task: asyncio.Task | None = None
        self._ws = None
        self._active = False
        self._keepalive_task: asyncio.Task | None = None
        self.reconnect_delay = 3.0
        self.keepalive_interval = 15.0

    def start(self) -> None:
        def _schedule() -> None:
            if self._task and not self._task.done():
                return
            self._active = True
            self._task = self.loop.create_task(self._runner())

        self.loop.call_soon_threadsafe(_schedule)

    def stop(self) -> None:
        def _cancel() -> None:
            self._active = False
            if self._task and not self._task.done():
                self._task.cancel()

        self.loop.call_soon_threadsafe(_cancel)

    async def _runner(self) -> None:
        uri = self.url_factory()
        while self._active:
            self._emit("status", {"state": "connecting", "detail": uri})
            final_state = {"state": "closed", "detail": None}
            try:
                async with ws_connect(uri, ping_interval=20, ping_timeout=20) as ws:
                    self._ws = ws
                    await ws.send('__listener__')
                    self._emit("status", {"state": "connected", "detail": uri})
                    self._keepalive_task = asyncio.create_task(self._keepalive(ws))
                    async for message in ws:
                        self._emit("message", message)
                final_state = {"state": "closed", "detail": "server closed"}
            except asyncio.CancelledError:
                final_state = {"state": "closed", "detail": "cancelled"}
                if self._ws is not None:
                    with contextlib.suppress(Exception):
                        await self._ws.close()
                self._active = False
            except WebSocketException as exc:
                final_state = {"state": "error", "detail": str(exc)}
            except Exception as exc:  # pragma: no cover - defensive catch
                final_state = {"state": "error", "detail": str(exc)}
            finally:
                if self._keepalive_task is not None:
                    self._keepalive_task.cancel()
                    with contextlib.suppress(Exception):
                        await self._keepalive_task
                    self._keepalive_task = None
                self._ws = None
                self._emit("status", final_state)

            if not self._active or final_state.get("detail") == "cancelled":
                break

            await asyncio.sleep(self.reconnect_delay)

        self._task = None

    async def _keepalive(self, ws) -> None:
        try:
            while self._active:
                await asyncio.sleep(self.keepalive_interval)
                if not self._active:
                    break
                try:
                    pong = ws.ping()
                    await asyncio.wait_for(pong, timeout=10)
                except Exception:
                    try:
                        await ws.send('__ping__')
                    except Exception:  # pragma: no cover - keep loop defensive
                        break
        except asyncio.CancelledError:
            pass


__all__ = ['AsyncLoopThread', 'WebSocketClient']
