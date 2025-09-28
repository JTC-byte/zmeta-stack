from typing import Set, Optional
import asyncio, json, time
from collections import deque

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import ValidationError

# Reuse your existing strict schema at repo root
from z_meta_schema import ZMeta

# Recorder (new)
from tools.recorder import recorder

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
        hub.d
