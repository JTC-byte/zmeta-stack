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
