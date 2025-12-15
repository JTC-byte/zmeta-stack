from __future__ import annotations

import asyncio
import json

import structlog
from pydantic import ValidationError

from .ingest import ingest_payload
from .metrics import metrics

log = structlog.get_logger("zmeta.udp")


class UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, queue: asyncio.Queue) -> None:
        self.queue = queue

    def datagram_received(self, data: bytes, addr) -> None:  # type: ignore[override]
        metrics.note_received()
        try:
            text = data.decode("utf-8", errors="ignore").strip()
            if text:
                self.queue.put_nowait(text)
        except asyncio.QueueFull:
            metrics.note_dropped()
            log.warning("UDP queue full; dropping packet", client=addr)
        except Exception:
            metrics.note_dropped()
            log.exception("Failed to process UDP datagram", client=addr)


async def udp_consumer(queue: asyncio.Queue) -> None:
    try:
        while True:
            raw = await queue.get()
            try:
                payload = json.loads(raw)
                try:
                    await ingest_payload(payload, context="udp")
                except ValidationError:
                    metrics.note_dropped()
                    continue
            except Exception:
                metrics.note_dropped()
                snippet = raw if isinstance(raw, str) else repr(raw)
                log.exception("Failed to process UDP payload", snippet=snippet[:200])
            finally:
                queue.task_done()
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception("UDP consumer crashed")


__all__ = ["UDPProtocol", "udp_consumer"]
