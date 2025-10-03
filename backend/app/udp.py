from __future__ import annotations

import asyncio
import json
import logging

from pydantic import ValidationError

from .ingest import ingest_payload
from .state import stats

log = logging.getLogger('zmeta.udp')


class UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, queue: asyncio.Queue) -> None:
        self.queue = queue

    def datagram_received(self, data: bytes, addr) -> None:  # type: ignore[override]
        stats.note_received()
        try:
            text = data.decode('utf-8', errors='ignore').strip()
            if text:
                self.queue.put_nowait(text)
        except asyncio.QueueFull:
            stats.note_dropped()
            log.warning('UDP queue full; dropping packet from %s', addr)
        except Exception:
            stats.note_dropped()
            log.exception('Failed to process UDP datagram from %s', addr)


async def udp_consumer(queue: asyncio.Queue) -> None:
    try:
        while True:
            raw = await queue.get()
            try:
                payload = json.loads(raw)
                try:
                    await ingest_payload(payload, context='udp')
                except ValidationError:
                    stats.note_dropped()
                    continue
            except Exception:
                stats.note_dropped()
                snippet = raw if isinstance(raw, str) else repr(raw)
                log.exception('Failed to process UDP payload (truncated): %s', snippet[:200])
            finally:
                queue.task_done()
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception('UDP consumer crashed')


__all__ = ['UDPProtocol', 'udp_consumer']
