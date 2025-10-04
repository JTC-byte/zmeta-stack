import asyncio
import logging

import pytest

from backend.app import ws
from backend.app.metrics import metrics


class FakeWebSocket:
    def __init__(self) -> None:
        self.client = ('127.0.0.1', 5555)
        self.accepted = False
        self.closed = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, message: str) -> None:
        # In this test the sender task never consumes messages.
        await asyncio.sleep(0)

    async def close(self) -> None:
        self.closed = True


def test_backpressure_disconnects_slow_client(caplog):
    caplog.set_level(logging.WARNING, logger='zmeta.ws')

    async def scenario() -> None:
        hub = ws.WSHub(queue_timeout=0.01, max_backpressure_retries=1)

        websocket = FakeWebSocket()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        queue.put_nowait('stale')

        sender_task = asyncio.create_task(asyncio.sleep(5))
        hub.clients[websocket] = ws.WSClient(websocket=websocket, queue=queue, sender=sender_task)

        snapshot = metrics.snapshot()
        try:
            await hub.broadcast_text('payload')

            after = metrics.snapshot()
            assert after.ws_dropped_total == snapshot.ws_dropped_total + 1
            assert websocket.closed is True
            assert websocket not in hub.clients
            assert any('backpressure' in record.getMessage() for record in caplog.records)
        finally:
            metrics.restore(snapshot)
            sender_task.cancel()
            try:
                await sender_task
            except asyncio.CancelledError:
                pass
            await hub.disconnect(websocket)

    asyncio.run(scenario())
