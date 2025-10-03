import asyncio
import copy
import json
from contextlib import suppress

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import lifespan
from backend.app.config import WS_GREETING
from backend.app.main import ZMeta, app, _dumps, deduper, hub, recorder, rules
from backend.app.state import stats


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def patch_udp_port(monkeypatch):
    monkeypatch.setattr(lifespan, "UDP_PORT", 0, raising=False)


@pytest.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.anyio
async def test_root_redirect(async_client):
    response = await async_client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/ui/live_map.html"


@pytest.mark.anyio
async def test_status_endpoint(async_client):
    response = await async_client.get("/api/v1/status")
    data = response.json()
    assert response.status_code == 200
    assert data["status"].startswith("ZMeta Backend")
    assert data["clients"] == len(hub.clients)


@pytest.mark.anyio
async def test_health_endpoint(async_client):
    response = await async_client.get("/api/v1/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert {"status", "clients", "udp_received_total"}.issubset(payload.keys())


@pytest.mark.anyio
async def test_ingest_endpoint(async_client, monkeypatch):
    stats_snapshot = copy.deepcopy(stats.__dict__)
    dedupe_snapshot = copy.deepcopy(deduper.__dict__)

    broadcast_calls: list[str] = []

    async def fake_broadcast(message: str) -> None:
        broadcast_calls.append(message)

    enqueue_calls: list[str] = []

    async def fake_enqueue(message: str) -> None:
        enqueue_calls.append(message)

    alerts = [
        {
            "type": "alert",
            "rule": "unit_test",
            "severity": "info",
            "loc": {"lat": 10.0, "lon": 20.0},
            "sensor_id": "sensor-test",
        }
    ]

    monkeypatch.setattr(hub, "broadcast_text", fake_broadcast, raising=False)
    monkeypatch.setattr(recorder, "enqueue", fake_enqueue, raising=False)
    monkeypatch.setattr(rules, "apply", lambda data: alerts, raising=False)
    deduper._seen.clear()

    payload = {
        "timestamp": "2025-01-01T00:00:00Z",
        "sensor_id": "sensor-test",
        "modality": "rf",
        "location": {"lat": 42.0, "lon": -71.0},
        "data": {"type": "rf_detection", "value": {"frequency_hz": 915_000_000}},
        "source_format": "zmeta",
        "schema_version": "1.0",
    }

    try:
        response = await async_client.post("/api/v1/ingest", json=payload)
        assert response.status_code == 200
        assert response.json()["ok"] is True

        expected = ZMeta.model_validate(payload)
        first_call = json.loads(broadcast_calls[0])
        assert first_call["sensor_id"] == expected.sensor_id
        assert first_call["sequence"] is not None
        assert json.loads(enqueue_calls[0])["sequence"] == first_call["sequence"]
        assert broadcast_calls[1] == _dumps(alerts[0])
        assert stats.validated_total == stats_snapshot["validated_total"] + 1
    finally:
        stats.__dict__.clear()
        stats.__dict__.update(stats_snapshot)
        deduper.__dict__.clear()
        deduper.__dict__.update(dedupe_snapshot)


def test_websocket_echo(monkeypatch):
    monkeypatch.setattr(lifespan, "UDP_PORT", 0, raising=False)

    async def _noop_consumer(queue):
        try:
            while True:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    monkeypatch.setattr(lifespan, "udp_consumer", _noop_consumer, raising=False)

    client = TestClient(app)
    try:
        with client.websocket_connect("/ws") as ws:
            greeting = ws.receive_text()
            assert greeting == WS_GREETING
            ws.send_text("ping")
            assert ws.receive_text() == "Echo: ping"
    finally:
        with suppress(Exception):
            client.close()
