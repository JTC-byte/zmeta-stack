import copy

import pytest

from backend.app import main


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_ingest_payload_broadcasts_and_records(monkeypatch):
    metrics_snapshot = main.metrics.snapshot()
    dedupe_snapshot = copy.deepcopy(main.deduper.__dict__)

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

    monkeypatch.setattr(main.hub, "broadcast_text", fake_broadcast)
    monkeypatch.setattr(main.recorder, "enqueue", fake_enqueue)
    monkeypatch.setattr(main.rules, "apply", lambda data: alerts)

    # Ensure dedupe state starts clean for the alert key
    main.deduper._seen.clear()

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
        result = await main._ingest_payload(payload, context="test")

        assert isinstance(result, main.ZMeta)
        assert result.sensor_id == "sensor-test"

        assert len(broadcast_calls) == 2
        assert broadcast_calls[0] == result.model_dump_json()
        assert enqueue_calls == [result.model_dump_json()]
        assert broadcast_calls[1] == main._dumps(alerts[0])

        after_snapshot = main.metrics.snapshot()
        assert after_snapshot.validated_total == metrics_snapshot.validated_total + 1
        assert after_snapshot.alerts_total == metrics_snapshot.alerts_total + 1
        assert main.deduper.total_checked == dedupe_snapshot["total_checked"] + 1
        assert main.deduper.total_suppressed == dedupe_snapshot["total_suppressed"]
    finally:
        main.metrics.restore(metrics_snapshot)
        main.deduper.__dict__.clear()
        main.deduper.__dict__.update(dedupe_snapshot)


@pytest.mark.anyio
async def test_ingest_payload_v11(monkeypatch):
    metrics_snapshot = main.metrics.snapshot()
    dedupe_snapshot = copy.deepcopy(main.deduper.__dict__)

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
            "sensor_id": "sensor-test-v11",
        }
    ]

    monkeypatch.setattr(main.hub, "broadcast_text", fake_broadcast)
    monkeypatch.setattr(main.recorder, "enqueue", fake_enqueue)
    monkeypatch.setattr(main.rules, "apply", lambda data: alerts)
    main.deduper._seen.clear()

    payload = {
        "schema_version": "1.1",
        "timestamp": "2025-01-01T00:00:00Z",
        "sensor_id": "sensor-test-v11",
        "modality": "rf",
        "location": {"lat": 42.0, "lon": -71.0},
        "data": {
            "type": "burst",
            "freq_hz": 915_000_000,
            "rssi_dbm": -52.0,
            "confidence": 0.93,
        },
        "provenance": {
            "source_format": "zmeta",
        },
    }

    try:
        result = await main._ingest_payload(payload, context="test-v11")

        assert isinstance(result, main.ZMeta)
        assert result.schema_version == "1.1"
        assert result.data.type == "rf_burst"
        assert result.data.value["frequency_hz"] == pytest.approx(915_000_000)
        assert result.data.value["rssi_dbm"] == pytest.approx(-52.0)
        assert result.provenance is not None
        assert result.provenance.source_format == "zmeta"

        assert len(broadcast_calls) == 2
        assert broadcast_calls[0] == result.model_dump_json()
        assert enqueue_calls == [result.model_dump_json()]
        assert broadcast_calls[1] == main._dumps(alerts[0])
    finally:
        main.metrics.restore(metrics_snapshot)
        main.deduper.__dict__.clear()
        main.deduper.__dict__.update(dedupe_snapshot)
