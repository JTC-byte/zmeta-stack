from __future__ import annotations

import time
from collections import Counter, deque
from typing import Optional


class Stats:
    def __init__(self) -> None:
        self.udp_received_total = 0
        self.validated_total = 0
        self.dropped_total = 0
        self.alerts_total = 0
        self.ws_sent_total = 0
        self.ws_dropped_total = 0
        self.sequence_counter = 0
        self.adapter_counts: Counter[str] = Counter()
        self.last_packet_ts: Optional[float] = None
        self._validated_ts = deque(maxlen=600)

    def note_received(self) -> None:
        self.udp_received_total += 1

    def note_dropped(self) -> None:
        self.dropped_total += 1

    def note_validated(self) -> None:
        self.validated_total += 1
        now = time.time()
        self.last_packet_ts = now
        self._validated_ts.append(now)

    def note_alert(self) -> None:
        self.alerts_total += 1

    def note_ws_sent(self) -> None:
        self.ws_sent_total += 1

    def note_ws_dropped(self) -> None:
        self.ws_dropped_total += 1

    def note_adapter(self, name: str) -> None:
        self.adapter_counts[name] += 1

    def next_sequence(self) -> int:
        self.sequence_counter += 1
        return self.sequence_counter

    def eps(self, window_s: int = 10) -> float:
        if not self._validated_ts:
            return 0.0
        now = time.time()
        cutoff = now - window_s
        count = sum(1 for ts in self._validated_ts if ts >= cutoff)
        return round(count / max(1, window_s), 2)




class AlertDeduper:
    def __init__(self, ttl_s: float = 3.0, max_keys: int = 10000) -> None:
        self.ttl = ttl_s
        self.max = max_keys
        self._seen: dict[str, float] = {}
        self.total_checked = 0
        self.total_suppressed = 0

    def _key(self, alert: dict) -> str:
        locate = alert.get('loc', {})
        lat = locate.get('lat')
        lon = locate.get('lon')
        if isinstance(lat, (int, float)):
            lat = round(float(lat), 4)
        if isinstance(lon, (int, float)):
            lon = round(float(lon), 4)
        return f"{alert.get('rule')}|{alert.get('sensor_id')}|{alert.get('severity')}|{lat},{lon}"

    def should_send(self, alert: dict) -> bool:
        self.total_checked += 1
        now = time.time()
        key = self._key(alert)
        seen_ts = self._seen.get(key)
        if seen_ts is not None and (now - seen_ts) < self.ttl:
            self.total_suppressed += 1
            return False
        self._seen[key] = now
        if len(self._seen) > self.max:
            cutoff = now - self.ttl
            self._seen = {k: ts for k, ts in self._seen.items() if ts >= cutoff}
        return True

    def metrics(self) -> dict[str, float]:
        return {
            'ttl_s': self.ttl,
            'checked_total': self.total_checked,
            'suppressed_total': self.total_suppressed,
        }


deduper = AlertDeduper(ttl_s=3.0)
