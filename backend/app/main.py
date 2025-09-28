# backend/app/main.py
from typing import Set, Optional
import asyncio, json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import ValidationError
from z_meta_schema import ZMeta  # your schema at repo root

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

@app.get("/")
async def root():
    return {"status": "ZMeta Backend running", "clients": len(hub.clients)}

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

# ----------------- HTTP ingest -----------------
@app.post("/ingest")
async def ingest(payload: dict):
    try:
        z = ZMeta.model_validate(payload)  # strict validation
    except ValidationError as ve:
        raise HTTPException(status_code=422, detail=ve.errors())
    await hub.broadcast_text(z.model_dump_json())
    return {"ok": True, "broadcast_to": len(hub.clients)}

# ----------------- UDP ingest (port 5005) -----------------
class UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    def datagram_received(self, data: bytes, addr):
        # Push raw payload to the async queue; parsing/validation happens in consumer
        try:
            text = data.decode("utf-8", errors="ignore").strip()
            if text:
                self.queue.put_nowait(text)
        except Exception:
            # swallow decode errors; could log here
            pass

async def udp_consumer(queue: asyncio.Queue):
    while True:
        raw = await queue.get()
        try:
            payload = json.loads(raw)
            # Validate against ZMeta
            z = ZMeta.model_validate(payload)
            # Broadcast to all WebSocket clients
            await hub.broadcast_text(z.model_dump_json())
        except Exception as e:
            # validation/parsing failure; could log
            # print(f"UDP packet rejected: {e}")
            pass
        finally:
            queue.task_done()

@app.on_event("startup")
async def startup():
    app.state.udp_queue = asyncio.Queue(maxsize=4096)
    loop = asyncio.get_running_loop()

    # Start UDP server on 0.0.0.0:5005
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDPProtocol(app.state.udp_queue),
        local_addr=("0.0.0.0", 5005)
    )
    app.state.udp_transport = transport
    # Start consumer task
    app.state.udp_consumer_task = asyncio.create_task(udp_consumer(app.state.udp_queue))

@app.on_event("shutdown")
async def shutdown():
    # Close UDP transport and cancel consumer task
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
