import time

from backend.app.main import AlertDeduper


def test_alert_deduper_suppresses_duplicate_alerts(monkeypatch):
    # Freeze time so repeated calls stay within TTL window
    fixed_time = time.time()
    monkeypatch.setattr('backend.app.state.time.time', lambda: fixed_time)

    deduper = AlertDeduper(ttl_s=5.0, max_keys=10)
    alert = {
        'rule': 'rf_strong_signal',
        'sensor_id': 'sensor-123',
        'severity': 'warn',
        'loc': {'lat': 35.2714, 'lon': -78.6376},
    }

    assert deduper.should_send(alert) is True
    assert deduper.should_send(alert) is False
