# backend/app/main.py
from __future__ import annotations
from typing import Set, Optional
import os
import asyncio, json, time, logging
import contextlib
from collections import deque, Counter
from dataclasses import dataclass
from datetime import datetime, date, timezone

from dotenv import load_dotenv

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from schemas.zmeta import ZMeta, SUPPORTED_SCHEMA_VERSIONS
from tools.recorder import recorder
from tools.rules import rules
from tools.ingest_adapters import adapt_to_zmeta

load_dotenv()


def _env_csv(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


UDP_HOST = os.getenv("ZMETA_UDP_HOST", "0.0.0.0")
UDP_PORT = int(os.getenv("ZMETA_UDP_PORT", "5005"))
UI_BASE_URL = os.getenv("ZMETA_UI_BASE_URL", "http://127.0.0.1:8000")
WS_GREETING = os.getenv("ZMETA_WS_GREETING", "Connected to ZMeta WebSocket")
ALLOWED_ORIGINS = _env_csv("ZMETA_CORS_ORIGINS", ["*"])
AUTH_HEADER = os.getenv("ZMETA_AUTH_HEADER", "x-zmeta-secret")
SHARED_SECRET = os.getenv("ZMETA_SHARED_SECRET", "").strip()
ENVIRONMENT = os.getenv("ZMETA_ENV", "dev")
WS_QUEUE_MAX = int(os.getenv("ZMETA_WS_QUEUE", "64"))

def _auth_enabled() -> bool:
    return bool(SHARED_SECRET)


def _verify_shared_secret(provided: str | None) -> bool:
    if not _auth_enabled():
        return True
    return provided == SHARED_SECRET


def _ui_url(path: str) -> str:
    base = UI_BASE_URL.rstrip('/')
    return f"{base}{path}"


# -----------------------------------------------------------------------------
# App & middleware
# -----------------------------------------------------------------------------
app = FastAPI(title="ZMeta Backend")

# Serve the dashboard folder (open /ui/live_map.html or /ui/ws_test.html)
app.mount("/ui", StaticFiles(directory="zmeta_map_dashboard", html=True), name="ui")

# CORS (dev-wide; restrict later if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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
@dataclass
class WSClient:
    websocket: WebSocket
    queue: asyncio.Queue[str]
    sender: asyncio.Task


class WSHub:
    def __init__(self):
        self._clients: dict[WebSocket, WSClient] = {}

    @property
    def clients(self) -> dict[WebSocket, WSClient]:
        return self._clients

    async def connect(self, ws: WebSocket):
        await ws.accept()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=WS_QUEUE_MAX)
        sender = asyncio.create_task(self._sender(ws, queue))
        self._clients[ws] = WSClient(websocket=ws, queue=queue, sender=sender)

    async def disconnect(self, ws: WebSocket, *, cancel_sender: bool = True):
        client = self._clients.pop(ws, None)
        if not client:
            return
        if cancel_sender:
            client.sender.cancel()
            with contextlib.suppress(Exception):
                await client.sender
        with contextlib.suppress(Exception):
            await ws.close()

    async def broadcast_text(self, msg: str):
        if not self._clients:
            return
        for ws, client in list(self._clients.items()):
            queue = client.queue
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                stats.note_ws_dropped()
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                try:
                    queue.put_nowait(msg)
                except asyncio.QueueFull:
                    stats.note_ws_dropped()
                    await self.disconnect(ws)

    async def _sender(self, ws: WebSocket, queue: asyncio.Queue[str]):
        try:
            while True:
                msg = await queue.get()
                try:
                    await ws.send_text(msg)
                    stats.note_ws_sent()
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            if ws in self._clients:
                await self.disconnect(ws, cancel_sender=False)


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
        self.ws_sent_total = 0
        self.ws_dropped_total = 0
        self.sequence_counter = 0
        self.adapter_counts: Counter[str] = Counter()
        self.last_packet_ts: Optional[float] = None
        self._validated_ts = deque(maxlen=600)  # ~10min @1Hz

    def note_received(self):
        self.udp_received_total += 1

    def note_dropped(self):
        self.dropped_total += 1

    def note_validated(self):
        self.validated_total += 1
        now = time.time()
        self.last_packet_ts = now
        self._validated_ts.append(now)

    def note_alert(self):
        self.alerts_total += 1

    def note_ws_sent(self):
        self.ws_sent_total += 1

    def note_ws_dropped(self):
        self.ws_dropped_total += 1

    def note_adapter(self, name: str):
        self.adapter_counts[name] += 1

    def next_sequence(self) -> int:
        self.sequence_counter += 1
        return self.sequence_counter

    def eps(self, window_s: int = 10) -> float:
        if not self._validated_ts:
            return 0.0
        now = time.time()
        cutoff = now - window_s
        n = sum(1 for t in self._validated_ts if t >= cutoff)
        return round(n / max(1, window_s), 2)

stats = Stats()

class AlertDeduper:
    """Short-window dedupe to avoid spamming identical alerts."""

    def __init__(self, ttl_s: float = 3.0, max_keys: int = 10000):
        self.ttl = ttl_s
        self.max = max_keys
        self._seen: dict[str, float] = {}
        self.total_checked = 0
        self.total_suppressed = 0

    def _key(self, a: dict) -> str:
        lat = a.get("loc", {}).get("lat")
        lon = a.get("loc", {}).get("lon")
        if isinstance(lat, (int, float)):
            lat = round(float(lat), 4)
        if isinstance(lon, (int, float)):
            lon = round(float(lon), 4)
        return f"{a.get(rule)}|{a.get(sensor_id)}|{a.get(severity)}|{lat},{lon}"

    def should_send(self, a: dict) -> bool:
        self.total_checked += 1
        now = time.time()
        k = self._key(a)
        ts = self._seen.get(k)
        if ts is not None and (now - ts) < self.ttl:
            self.total_suppressed += 1
            return False
        self._seen[k] = now
        if len(self._seen) > self.max:
            cutoff = now - self.ttl
            self._seen = {k: t for k, t in self._seen.items() if t >= cutoff}
        return True

    def metrics(self) -> dict[str, float]:
        return {"ttl_s": self.ttl, "checked_total": self.total_checked, "suppressed_total": self.total_suppressed}

deduper = AlertDeduper(ttl_s=3.0)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _validate_or_adapt(payload: dict) -> ZMeta:
    """Validate to ZMeta; if that fails, normalize via adapter then validate."""
    adapter_name = 'native'
    try:
        z = ZMeta.model_validate(payload)
    except ValidationError:
        adapted = adapt_to_zmeta(payload)
        if adapted is None:
            raise
        adapter_name, adapted_payload = adapted
        z = ZMeta.model_validate(adapted_payload)
    else:
        adapter_name = 'native'

    if z.sequence is None:
        z = z.model_copy(update={'sequence': stats.next_sequence()})

    stats.note_adapter(adapter_name)
    return z

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def home_redirect():
    # Open the dashboard by default
    return RedirectResponse(url="/ui/live_map.html", status_code=307)

# Alias classic /favicon.ico to our UI favicon
@app.get("/favicon.ico", include_in_schema=False)
async def favicon_redirect():
    return RedirectResponse(url="/ui/favicon.svg")

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
        "ws_queue_max": WS_QUEUE_MAX,
        "ws_sent_total": stats.ws_sent_total,
        "ws_dropped_total": stats.ws_dropped_total,
        "auth_mode": 'shared_secret' if _auth_enabled() else 'disabled',
        "auth_header": AUTH_HEADER if _auth_enabled() else None,
        "allowed_origins": ALLOWED_ORIGINS,
        "environment": ENVIRONMENT,
        "supported_schema_versions": sorted(SUPPORTED_SCHEMA_VERSIONS),
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
    provided = websocket.headers.get(AUTH_HEADER) or websocket.query_params.get('secret')
    if not _verify_shared_secret(provided):
        await websocket.close(code=4401)
        return

    await hub.connect(websocket)
    await websocket.send_text(WS_GREETING)
    try:
        while True:
            data = await websocket.receive_text()  # echo for manual testing
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.disconnect(websocket)

@app.post("/ingest")
async def ingest(request: Request, payload: dict):
    if _auth_enabled():
        provided = request.headers.get(AUTH_HEADER) or request.query_params.get('secret')
        if not _verify_shared_secret(provided):
            raise HTTPException(status_code=401, detail='Unauthorized')

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
    try:
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
                    log.exception('rules.apply failed (udp)')
                    alerts = []
                for alert in alerts:
                    if deduper.should_send(alert):
                        await hub.broadcast_text(_dumps(alert))
                        stats.note_alert()

            except Exception:
                stats.note_dropped()
            finally:
                q.task_done()
    except asyncio.CancelledError:
        pass



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
        local_addr=(UDP_HOST, UDP_PORT),
    )
    app.state.udp_transport = transport
    app.state.udp_consumer_task = asyncio.create_task(udp_consumer(app.state.udp_queue))

    # Helpful links
    print(f"\nLive map:  {_ui_url('/ui/live_map.html')}")
    print(f"WS test:   {_ui_url('/ui/ws_test.html')}")
    print(f"Health:    {_ui_url('/healthz')}\n")

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
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    await recorder.stop()




