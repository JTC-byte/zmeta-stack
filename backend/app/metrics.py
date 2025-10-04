from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from threading import RLock
from typing import Any, Dict, Optional

from collections import Counter

from .state import Stats


@dataclass(frozen=True)
class MetricsSnapshot:
    udp_received_total: int
    validated_total: int
    dropped_total: int
    alerts_total: int
    ws_sent_total: int
    ws_dropped_total: int
    sequence_counter: int
    last_packet_ts: float | None
    adapter_counts: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MetricsProvider:
    """Thread-safe wrapper providing access to Stats counters and metrics."""

    def __init__(self, *, stats: Stats | None = None) -> None:
        self._stats = stats or Stats()
        self._lock = RLock()

    # --- mutation helpers ---
    def note_received(self) -> None:
        with self._lock:
            self._stats.note_received()

    def note_dropped(self) -> None:
        with self._lock:
            self._stats.note_dropped()

    def note_validated(self) -> None:
        with self._lock:
            self._stats.note_validated()

    def note_alert(self) -> None:
        with self._lock:
            self._stats.note_alert()

    def note_ws_sent(self) -> None:
        with self._lock:
            self._stats.note_ws_sent()

    def note_ws_dropped(self) -> None:
        with self._lock:
            self._stats.note_ws_dropped()

    def note_adapter(self, name: str) -> None:
        with self._lock:
            self._stats.note_adapter(name)

    def next_sequence(self) -> int:
        with self._lock:
            return self._stats.next_sequence()

    # --- observation helpers ---
    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(
                udp_received_total=self._stats.udp_received_total,
                validated_total=self._stats.validated_total,
                dropped_total=self._stats.dropped_total,
                alerts_total=self._stats.alerts_total,
                ws_sent_total=self._stats.ws_sent_total,
                ws_dropped_total=self._stats.ws_dropped_total,
                sequence_counter=self._stats.sequence_counter,
                last_packet_ts=self._stats.last_packet_ts,
                adapter_counts=dict(self._stats.adapter_counts),
            )

    def eps(self, window_s: int = 10) -> float:
        with self._lock:
            return self._stats.eps(window_s)

    def last_packet_age(self, *, now: Optional[float] = None) -> Optional[float]:
        with self._lock:
            ts = self._stats.last_packet_ts
        if ts is None:
            return None
        current = now if now is not None else time.time()
        return max(0.0, round(current - ts, 2))

    # --- lifecycle helpers ---
    def restore(self, snapshot: MetricsSnapshot) -> None:
        with self._lock:
            self._stats.udp_received_total = snapshot.udp_received_total
            self._stats.validated_total = snapshot.validated_total
            self._stats.dropped_total = snapshot.dropped_total
            self._stats.alerts_total = snapshot.alerts_total
            self._stats.ws_sent_total = snapshot.ws_sent_total
            self._stats.ws_dropped_total = snapshot.ws_dropped_total
            self._stats.sequence_counter = snapshot.sequence_counter
            self._stats.last_packet_ts = snapshot.last_packet_ts
            self._stats.adapter_counts = Counter(snapshot.adapter_counts)
            # preserve validated timestamps deque; safest to clear when restoring
            self._stats._validated_ts.clear()

    def reset(self) -> None:
        self.restore(
            MetricsSnapshot(
                udp_received_total=0,
                validated_total=0,
                dropped_total=0,
                alerts_total=0,
                ws_sent_total=0,
                ws_dropped_total=0,
                sequence_counter=0,
                last_packet_ts=None,
                adapter_counts={},
            )
        )


metrics = MetricsProvider()


__all__ = ['MetricsProvider', 'MetricsSnapshot', 'metrics']
