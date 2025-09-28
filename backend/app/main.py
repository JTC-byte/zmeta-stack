from typing import Set, Optional
import asyncio, json, time
from collections import deque

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import ValidationError

# Reuse your existing strict schema at repo root
from z_meta_schema import ZMeta

app = FastAPI(title="ZMeta Backend")

# ----------------- WebSocket hub -----------------
class WSHub:
    def __init__(self):
        self.clients: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast_text(self, msg: str):
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

hub = WSHub()

# ----------------- Basic stats -----------------
class Stats:
    def __init__(self):
        self.udp_received_total = 0
        self.validated_total = 0
        self.dropped_total = 0
        self.last_packet_ts: Optional[float] = None
        self._validated_ts = deque(maxlen=600)  # timestamps of last ~10 min

    def note_received(self):
        self.udp_received_total += 1

    def note_validated(self):
        self.validated_total += 1
        now = time.time()
        self.last_packet_ts = now
        self._validated_ts.append(now)

    def note_dropped(self):
        self.dropped_total += 1

    def eps(self, window_s: int = 10) -> float:
        if not self._validated_ts:
            return 0.0
        now = time.time()
        cutoff = now - window_s
        n = sum(1 for t in self._validated_ts if t >= cutoff)
        return round(n / max(1, window_s), 2)

stats = Stats()

# ----------------- Routes -----------------
@app.get("/")
async def root():
    return {"status": "ZMeta Backend running", "clients": len(hub.clients)}

@app.get("/healthz")
async def healthz():
    last_age = None
    if stats.last_packet_ts is not None:
        last_age = round(max(0.0, time.time() - stats.last_packet_ts), 2)
    return {
        "status": "ok",
        "clients": len(hub.clients),
        "udp_received_total": stats.udp_received_total,
        "validated_total": stats.validated_total,
        "dropped_total": stats.dropped_total,
        "eps_1s": stats.eps(1),
        "eps_10s": stats.eps(10),
        "last_packet_age_s": last_age,
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await hub.connect(websocket)
    await websocket.send_text("✅ Connected to ZMeta WebSocket")
    try:
        while True:
            data = await websocket.receive_text()
            # optional echo for manual testing
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        hub.disconnect(websocket)
    except Exception:
        hub.disconnect(websocket)

@app.post("/ingest")
async def ingest(payload: dict):
    try:
        z = ZMeta.model_validate(payload)  # strict validation
    except ValidationError as ve:
        raise HTTPException(status_code=422, detail=ve.errors())
    await hub.broadcast_text(z.model_dump_json())
    stats.note_validated()
    return {"ok": True, "broadcast_to": len(hub.clients)}

# ----------------- UDP ingest (port 5005) -----------------
class UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    def datagram_received(self, data: bytes, addr):
        stats.note_received()
        try:
            text = data.decode("utf-8", errors="ignore").strip()
            if text:
                self.queue.put_nowait(text)
        except Exception:
            pass

async def udp_consumer(queue: asyncio.Queue):
    while True:
        raw = await queue.get()
        try:
            payload = json.loads(raw)
            z = ZMeta.model_validate(payload)
            await hub.broadcast_text(z.model_dump_json())
            stats.note_validated()
        except Exception:
            stats.note_dropped()
        finally:
            queue.task_done()

@app.on_event("startup")
async def startup():
    app.state.udp_queue = asyncio.Queue(maxsize=4096)
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: UDPProtocol(app.state.udp_queue),
        local_addr=("0.0.0.0", 5005)
    )
    app.state.udp_transport = transport
    app.state.udp_consumer_task = asyncio.create_task(udp_consumer(app.state.udp_queue))

@app.on_event("shutdown")
async def shutdown():
    transport: Optional[asyncio.transports.DatagramTransport] = getattr(app.state, "udp_transport", None)
    if transport is not None:
        transport.close()
    task: Optional[asyncio.Task] = getattr(app.state, "udp_consumer_task", None)
    if task:
        task.cancel()
        try:
            await task
        except Exception:
            pass
