# backend/app/main.py
from __future__ import annotations
from typing import Set, Optional
import asyncio, json, time, logging
from collections import deque
from datetime import datetime, date, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from z_meta_schema import ZMeta
from tools.recorder import recorder
from tools.rules import rules
from tools.ingest_adapters import adapt_to_zmeta

# -----------------------------------------------------------------------------
# App & middleware
# -----------------------------------------------------------------------------
app = FastAPI(title="ZMeta Backend")

# Serve the dashboard folder (open /ui/live_map.html or /ui/ws_test.html)
app.mount("/ui", StaticFiles(directory="zmeta_map_dashboard", html=True), name="ui")

# CORS (dev-wide; restrict later if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

log = logging.getLogger("zmeta")

# -----------------------------------------------------------------------------
# JSON utilities (datetime-safe)
# -----------------------------------------------------------------------------
def _json_default(o):
    if isinstance(o, (datetime, date)):
        try:
            if isinstance(o, datetime) and o.tzinfo is None:
                o = o.replace(tzinfo=timezone.utc)
            s = o.isoformat()
            return s.replace("+00:00", "Z")
        except Exception:
            return str(o)
    return str(o)

def _dumps(obj) -> str:
    return json.dumps(obj, default=_json_default, separators=(",", ":"), ensure_ascii=False)

# -----------------------------------------------------------------------------
# WebSocket hub
# -----------------------------------------------------------------------------
class WSHub:
    def __init__(self):
        self.clients: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast_text(self, msg: str):
        dead: list[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

hub = WSHub()

# -----------------------------------------------------------------------------
# Stats
# -----------------------------------------------------------------------------
class Stats:
    def __init__(self):
        self.udp_received_total = 0
        self.validated_total = 0
        self.dropped_total = 0
        self.alerts_total = 0
        self.last_packet_ts: Optional[float] = None
        self._validated_ts = deque(maxlen=600)  # ~10min @1Hz

    def note_received(self):  self.udp_received_total += 1
    def note_dropped(self):   self.dropped_total += 1
    def note_validated(self):
        self.validated_total += 1
        now = time.time()
        self.last_packet_ts = now
        self._validated_ts.append(now)
    def note_alert(self):     self.alerts_total += 1

    def eps(self, window_s: int = 10) -> float:
        if not self._validated_ts:
            return 0.0
        now = time.time()
        cutoff = now - window_s
        n = sum(1 for t in self._validated_ts if t >= cutoff)
        return round(n / max(1, window_s), 2)

stats = Stats()

# -----------------------------------------------------------------------------
# Short-window alert de-dup
# -----------------------------------------------------------------------------
class AlertDeduper:
    def __init__(self, ttl_s: float = 3.0, max_keys: int = 10000):
        self.ttl = ttl_s
        self.max = max_keys
        self._seen: dict[str, float] = {}

    def _key(self, a: dict) -> str:
        lat = a.get("loc", {}).get("lat")
        lon = a.get("loc", {}).get("lon")
        if isinstance(lat, (int, float)): lat = round(float(lat), 4)
        if isinstance(lon, (int, float)): lon = round(float(lon), 4)
        return f"{a.get('rule')}|{a.get('sensor_id')}|{a.get('severity')}|{lat},{lon}"

    def should_send(self, a: dict) -> bool:
        now = time.time()
        k = self._key(a)
        ts = self._seen.get(k)
        if ts is not None and (now - ts) < self.ttl:
            return False
        self._seen[k] = now
        if len(self._seen) > self.max:
            cutoff = now - self.ttl
            self._seen = {k: t for k, t in self._seen.items() if t >= cutoff}
        return True

deduper = AlertDeduper(ttl_s=3.0)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _validate_or_adapt(payload: dict) -> ZMeta:
    """Validate to ZMeta; if that fails, normalize via adapter then validate."""
    try:
        return ZMeta.model_validate(payload)
    except ValidationError:
        adapted = adapt_to_zmeta(payload)
        if adapted is None:
            raise
        return ZMeta.model_validate(adapted)

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def home_redirect():
    # Open the dashboard by default
    return RedirectResponse(url="/ui/live_map.html", status_code=307)

@app.get("/api")
def api_root():
    return {"status": "ZMeta Backend running", "clients": len(hub.clients)}

@app.get("/healthz")
async def healthz():
    age = None if stats.last_packet_ts is None else round(max(0.0, time.time() - stats.last_packet_ts), 2)
    return {
        "status": "ok",
        "clients": len(hub.clients),
        "udp_received_total": stats.udp_received_total,
        "validated_total": stats.validated_total,
        "dropped_total": stats.dropped_total,
        "alerts_total": stats.alerts_total,
        "eps_1s": stats.eps(1),
        "eps_10s": stats.eps(10),
        "last_packet_age_s": age,
    }

@app.get("/rules")
async def rules_get():
    return {"count": len(rules.set.rules), "rules": [r.name for r in rules.set.rules]}

@app.post("/rules/reload")
async def rules_reload():
    rules.load()
    return {"reloaded": True, "count": len(rules.set.rules)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await hub.connect(websocket)
    await websocket.send_text("✅ Connected to ZMeta WebSocket")
    try:
        while True:
            data = await websocket.receive_text()  # echo for manual testing
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        hub.disconnect(websocket)
    except Exception:
        hub.disconnect(websocket)

@app.post("/ingest")
async def ingest(payload: dict):
    # Validate/normalize
    try:
        z = _validate_or_adapt(payload)
    except ValidationError as ve:
        raise HTTPException(status_code=422, detail=ve.errors())

    # Broadcast & record
    data_json = z.model_dump_json()
    data_dict = z.model_dump()
    await hub.broadcast_text(data_json)
    await recorder.enqueue(data_json)
    stats.note_validated()

    # Apply rules defensively
    try:
        alerts = rules.apply(data_dict)
    except Exception:
        log.exception("rules.apply failed")
        alerts = []

    for alert in alerts:
        if deduper.should_send(alert):
            await hub.broadcast_text(_dumps(alert))
            stats.note_alert()

    return {"ok": True, "broadcast_to": len(hub.clients)}

# -----------------------------------------------------------------------------
# UDP ingest (127.0.0.1:5005)
# -----------------------------------------------------------------------------
class UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, q: asyncio.Queue):
        self.q = q
    def datagram_received(self, data: bytes, addr):
        stats.note_received()
        try:
            text = data.decode("utf-8", errors="ignore").strip()
            if text:
                self.q.put_nowait(text)
        except Exception:
            pass

async def udp_consumer(q: asyncio.Queue):
    while True:
        raw = await q.get()
        try:
            payload = json.loads(raw)
            try:
                z = _validate_or_adapt(payload)
            except ValidationError:
                stats.note_dropped()
                continue

            data_json = z.model_dump_json()
            data_dict = z.model_dump()

            await hub.broadcast_text(data_json)
            await recorder.enqueue(data_json)
            stats.note_validated()

            try:
                alerts = rules.apply(data_dict)
            except Exception:
                log.exception("rules.apply failed (udp)")
                alerts = []
            for alert in alerts:
                if deduper.should_send(alert):
                    await hub.broadcast_text(_dumps(alert))
                    stats.note_alert()

        except Exception:
            stats.note_dropped()
        finally:
            q.task_done()

# -----------------------------------------------------------------------------
# Lifecycle
# -----------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    rules.load()
    app.state.udp_queue = asyncio.Queue(maxsize=4096)

    # recorder writer task
    await recorder.start()

    # UDP server
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: UDPProtocol(app.state.udp_queue),
        local_addr=("0.0.0.0", 5005),
    )
    app.state.udp_transport = transport
    app.state.udp_consumer_task = asyncio.create_task(udp_consumer(app.state.udp_queue))

    # Helpful links
    print("\n📍 Live map:  http://127.0.0.1:8000/ui/live_map.html")
    print("🧪 WS test:   http://127.0.0.1:8000/ui/ws_test.html")
    print("❤️ Health:    http://127.0.0.1:8000/healthz\n")

@app.on_event("shutdown")
async def shutdown():
    transport: Optional[asyncio.transports.DatagramTransport] = getattr(app.state, "udp_transport", None)
    if transport:
        transport.close()
    task: Optional[asyncio.Task] = getattr(app.state, "udp_consumer_task", None)
    if task:
        task.cancel()
        try:
            await task
        except Exception:
            pass
    await recorder.stop()
