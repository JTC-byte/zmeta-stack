from datetime import datetime

import pytest

from tools.translators.klv_to_zmeta import klv_to_zmeta


def test_klv_payload_translates_to_zmeta():
    sample = {
        "sensor_id": "klv_source_001",
        "timestamp": "2025-02-01T18:30:00Z",
        "targetLatitude": 35.0005,
        "targetLongitude": -78.0005,
        "targetAltitude": 120.0,
        "sensorType": "RF",
        "platformHeading": 90.0,
        "signal_strength": -55.0,
    }

    zmeta = klv_to_zmeta(sample)

    assert zmeta.modality == "rf"
    assert zmeta.location.lat == pytest.approx(35.0005)
    assert zmeta.location.lon == pytest.approx(-78.0005)
    assert zmeta.data.value["signal_strength"] == pytest.approx(-55.0)
    assert zmeta.source_format == "KLV"


def test_klv_missing_timestamp_gets_default():
    sample = {
        "targetLatitude": 0.5,
        "targetLongitude": 1.5,
        "sensorType": "EO",
    }

    zmeta = klv_to_zmeta(sample)
    assert isinstance(zmeta.timestamp, datetime)
    assert zmeta.timestamp.tzinfo is not None
    assert zmeta.modality == "eo"
