from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import Dict

from fastapi import WebSocket

from .config import WS_QUEUE_MAX
from .state import stats

log = logging.getLogger('zmeta.ws')


@dataclass
class WSClient:
    websocket: WebSocket
    queue: asyncio.Queue[str]
    sender: asyncio.Task


class WSHub:
    def __init__(self) -> None:
        self._clients: Dict[WebSocket, WSClient] = {}

    @property
    def clients(self) -> Dict[WebSocket, WSClient]:
        return self._clients

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=WS_QUEUE_MAX)
        sender = asyncio.create_task(self._sender(websocket, queue))
        self._clients[websocket] = WSClient(websocket=websocket, queue=queue, sender=sender)

    async def disconnect(self, websocket: WebSocket, *, cancel_sender: bool = True) -> None:
        client = self._clients.pop(websocket, None)
        if not client:
            return
        if cancel_sender:
            client.sender.cancel()
            with contextlib.suppress(Exception):
                await client.sender
        with contextlib.suppress(Exception):
            await websocket.close()

    async def broadcast_text(self, message: str) -> None:
        if not self._clients:
            return
        for ws, client in list(self._clients.items()):
            queue = client.queue
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                stats.note_ws_dropped()
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    stats.note_ws_dropped()
                    await self.disconnect(ws)

    async def _sender(self, websocket: WebSocket, queue: asyncio.Queue[str]) -> None:
        try:
            while True:
                message = await queue.get()
                try:
                    await websocket.send_text(message)
                    stats.note_ws_sent()
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception:
            client = getattr(websocket, 'client', None)
            log.exception('WebSocket sender error for %s', client)
        finally:
            if websocket in self._clients:
                await self.disconnect(websocket, cancel_sender=False)


hub = WSHub()
