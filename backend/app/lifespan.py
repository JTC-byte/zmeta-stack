from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import AsyncIterator

from fastapi import FastAPI

from tools.recorder import recorder
from tools.rules import rules

from .config import UDP_HOST, UDP_PORT, UDP_QUEUE_MAX, ui_url
from .udp import UDPProtocol, udp_consumer

log = logging.getLogger('zmeta.lifespan')


@contextlib.asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    rules.load()
    queue: asyncio.Queue = asyncio.Queue(maxsize=UDP_QUEUE_MAX)
    app.state.udp_queue = queue

    await recorder.start()

    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: UDPProtocol(queue),
        local_addr=(UDP_HOST, UDP_PORT),
    )
    app.state.udp_transport = transport
    app.state.udp_consumer_task = asyncio.create_task(udp_consumer(queue))

    print(f"\nLive map:  {ui_url('/ui/live_map.html')}")
    print(f"WS test:   {ui_url('/ui/ws_test.html')}")
    print(f"Health:    {ui_url('/healthz')}\n")

    try:
        yield
    finally:
        transport = getattr(app.state, 'udp_transport', None)
        if transport:
            transport.close()
        task = getattr(app.state, 'udp_consumer_task', None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception('UDP consumer task shutdown failed')
        await recorder.stop()


__all__ = ['app_lifespan']
