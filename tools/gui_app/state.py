from __future__ import annotations

"""Shared GUI state helpers and constants."""

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Tuple

MODALITY_COLORS: dict[str, str] = {
    "rf": "#007aff",
    "thermal": "#ff3b30",
    "eo": "#34c759",
    "ir": "#ff9500",
    "acoustic": "#8e8e93",
    "default": "#5856d6",
}

SEVERITY_COLORS: dict[str, str] = {
    "crit": "#ff3b30",
    "warn": "#ff9500",
    "info": "#007aff",
    "default": "#007aff",
}


@dataclass
class AlertStore:
    """Track the most recent alert payloads."""

    max_entries: int = 200
    _entries: Deque[dict[str, Any]] = field(init=False)
    total_received: int = 0

    def __post_init__(self) -> None:
        self._entries = deque(maxlen=self.max_entries)

    def push(self, entry: dict[str, Any]) -> None:
        self._entries.appendleft(entry)
        self.total_received += 1

    def __iter__(self) -> Iterable[dict[str, Any]]:
        return iter(self._entries)

    def snapshot(self) -> List[dict[str, Any]]:
        return list(self._entries)


@dataclass
class TrackStore:
    """Maintain the latest track payloads and coordinate history."""

    max_trail_points: int = 60
    items: Dict[str, dict[str, Any]] = field(default_factory=dict)
    history: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)

    def upsert(self, track_id: str, lat: float, lon: float, payload: dict[str, Any]) -> None:
        self.items[track_id] = payload
        history = self.history.setdefault(track_id, [])
        history.append((lat, lon))
        if len(history) > self.max_trail_points:
            del history[:-self.max_trail_points]


@dataclass
class LogBuffer:
    """Keep an in-memory rolling log for the debug view."""

    max_entries: int = 500
    _entries: Deque[str] = field(init=False)

    def __post_init__(self) -> None:
        self._entries = deque(maxlen=self.max_entries)

    def append(self, message: str) -> None:
        self._entries.append(message)

    def clear(self) -> None:
        self._entries.clear()

    def snapshot(self) -> List[str]:
        return list(self._entries)


def resolve_track_id(data: dict[str, Any]) -> str:
    for key in ("tracking_id", "pid", "sensor_id"):
        value = data.get(key)
        if value:
            return str(value)
    data_type = data.get("data", {}).get("type", "unknown")
    sensor = data.get("sensor_id", "sensor")
    return f"{sensor}:{data_type}"


def modality_color(modality: str) -> str:
    return MODALITY_COLORS.get(modality.lower(), MODALITY_COLORS["default"])


def severity_color(severity: str) -> str:
    return SEVERITY_COLORS.get(severity.lower(), SEVERITY_COLORS["default"])


def severity_dot(severity: str) -> str:
    return '?'


__all__ = [
    'AlertStore',
    'LogBuffer',
    'MODALITY_COLORS',
    'SEVERITY_COLORS',
    'TrackStore',
    'modality_color',
    'resolve_track_id',
    'severity_color',
    'severity_dot',
]
