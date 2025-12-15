from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Dict, List

import structlog
from fastapi import WebSocket

from .config import WS_QUEUE_MAX
from .metrics import metrics

log = structlog.get_logger("zmeta.ws")


@dataclass
class WSClient:
    websocket: WebSocket
    queue: asyncio.Queue[str]
    sender: asyncio.Task


class WSHub:
    def __init__(self, *, queue_timeout: float = 0.25, max_backpressure_retries: int = 3) -> None:
        self._clients: Dict[WebSocket, WSClient] = {}
        self._drop_counts: Dict[WebSocket, int] = {}
        self.queue_put_timeout = queue_timeout
        self.max_backpressure_retries = max_backpressure_retries

    @property
    def clients(self) -> Dict[WebSocket, WSClient]:
        return self._clients

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=WS_QUEUE_MAX)
        sender = asyncio.create_task(self._sender(websocket, queue))
        self._clients[websocket] = WSClient(websocket=websocket, queue=queue, sender=sender)
        self._drop_counts.pop(websocket, None)

    async def disconnect(self, websocket: WebSocket, *, cancel_sender: bool = True) -> None:
        client = self._clients.pop(websocket, None)
        self._drop_counts.pop(websocket, None)
        if not client:
            return
        if cancel_sender:
            client.sender.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await client.sender
        with contextlib.suppress(Exception):
            await websocket.close()

    async def broadcast_text(self, message: str) -> None:
        if not self._clients:
            return
        for ws, client in list(self._clients.items()):
            queue = client.queue
            try:
                await asyncio.wait_for(queue.put(message), timeout=self.queue_put_timeout)
                self._drop_counts.pop(ws, None)
            except asyncio.TimeoutError:
                await self._handle_backpressure(ws, client, message, reason="put-timeout")
            except asyncio.CancelledError:
                raise
            except Exception:
                metrics.note_ws_dropped()
                log.exception("Unexpected error queuing WS broadcast", client=self._client_label(ws))
                await self.disconnect(ws)

    async def _handle_backpressure(
        self,
        websocket: WebSocket,
        client: WSClient,
        message: str,
        *,
        reason: str,
    ) -> None:
        queue = client.queue
        metrics.note_ws_dropped()
        drop_count = self._drop_counts.get(websocket, 0) + 1
        self._drop_counts[websocket] = drop_count
        queue_size = queue.qsize()
        log.warning(
            "WS backpressure detected",
            client=self._client_label(websocket),
            reason=reason,
            queue_size=queue_size,
            queue_max=queue.maxsize,
            drops=drop_count,
        )
        with contextlib.suppress(asyncio.QueueEmpty):
            queue.get_nowait()
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            log.warning(
                "WS queue saturated; disconnecting slow client",
                client=self._client_label(websocket),
                queue_size=queue.qsize(),
                queue_max=queue.maxsize,
            )
            await self.disconnect(websocket)
            return
        if drop_count >= self.max_backpressure_retries:
            log.warning(
                "WS backpressure threshold reached; closing client",
                client=self._client_label(websocket),
                drops=drop_count,
            )
            await self.disconnect(websocket)

    async def _sender(self, websocket: WebSocket, queue: asyncio.Queue[str]) -> None:
        try:
            while True:
                message = await queue.get()
                try:
                    await websocket.send_text(message)
                    metrics.note_ws_sent()
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception:
            client = getattr(websocket, "client", None)
            log.exception("WebSocket sender error", client=client)
        finally:
            if websocket in self._clients:
                await self.disconnect(websocket, cancel_sender=False)

    def stats(self) -> dict[str, object]:
        clients: List[dict[str, object]] = []
        for ws, client in self._clients.items():
            clients.append(
                {
                    "client": self._client_label(ws),
                    "queue_size": client.queue.qsize(),
                    "queue_max": client.queue.maxsize,
                    "drops": self._drop_counts.get(ws, 0),
                }
            )
        return {
            "clients_total": len(self._clients),
            "drops_total": sum(self._drop_counts.values()),
            "max_queue": WS_QUEUE_MAX,
            "clients": clients,
        }

    @staticmethod
    def _client_label(websocket: WebSocket) -> str:
        client = getattr(websocket, "client", None)
        if not client:
            return "unknown"
        host, port = client
        return f"{host}:{port}"


hub = WSHub()

