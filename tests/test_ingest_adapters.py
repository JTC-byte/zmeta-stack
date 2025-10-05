import pytest

from schemas.zmeta import ZMeta, SUPPORTED_SCHEMA_VERSIONS
from tools.ingest_adapters import adapt_to_zmeta


@pytest.fixture()
def simulated_rf_payload() -> dict:
    return {
        "timestamp": "2025-02-01T12:00:00Z",
        "sensor_id": "sim_rf_01",
        "modality": "rf",
        "location": {"lat": 35.2714, "lon": -78.6376, "alt": 145.0},
        "data": {"type": "frequency", "value": 915.2, "units": "MHz", "rssi_dbm": -42.5},
        "source_format": "simulated_json_v1",
        "confidence": 0.92,
    }


@pytest.fixture()
def simulated_thermal_payload() -> dict:
    return {
        "timestamp": "2025-02-01T12:00:00Z",
        "sensor_id": "sim_thermal_01",
        "modality": "thermal",
        "location": {"lat": 35.2714, "lon": -78.6376, "alt": 145.0},
        "data": {"type": "hotspot", "value": 63.5},
        "source_format": "simulated_json_v1",
    }


def test_adapt_rf_payload(simulated_rf_payload):
    result = adapt_to_zmeta(simulated_rf_payload)
    assert result is not None
    adapter, adapted = result
    assert adapter == "simulated_v1_rf"
    zmeta = ZMeta.model_validate(adapted)
    assert zmeta.modality == "rf"
    assert adapted["data"]["value"]["frequency_hz"] == 915200000
    assert adapted["data"]["value"]["rssi_dbm"] == pytest.approx(-42.5)
    assert adapted["confidence"] == pytest.approx(0.92)
    assert adapted["schema_version"] in SUPPORTED_SCHEMA_VERSIONS


def test_adapt_thermal_payload(simulated_thermal_payload):
    result = adapt_to_zmeta(simulated_thermal_payload)
    assert result is not None
    adapter, adapted = result
    assert adapter == "simulated_v1_thermal"
    zmeta = ZMeta.model_validate(adapted)
    assert zmeta.modality == "thermal"
    assert adapted["data"]["value"]["temp_c"] == pytest.approx(63.5)
    assert adapted["schema_version"] in SUPPORTED_SCHEMA_VERSIONS


def test_adapt_unknown_payload_returns_none():
    payload = {"sensor_id": "unknown", "data": {"type": "mystery"}}
    assert adapt_to_zmeta(payload) is None


def test_adapt_klv_like_payload():
    payload = {
        "sensor_id": "klv_source_001",
        "timestamp": "2025-02-01T18:30:00Z",
        "targetLatitude": 35.0005,
        "targetLongitude": -78.0005,
        "targetAltitude": 120.0,
        "sensorType": "RF",
        "platformHeading": 45.0,
        "signal_strength": -52.0,
    }
    result = adapt_to_zmeta(payload)
    assert result is not None
    adapter, adapted = result
    assert adapter == "klv_like"
    zmeta = ZMeta.model_validate(adapted)
    assert zmeta.modality == "rf"
    assert zmeta.source_format == "KLV"
    assert zmeta.location.lat == pytest.approx(35.0005)
    assert adapted["schema_version"] in SUPPORTED_SCHEMA_VERSIONS

