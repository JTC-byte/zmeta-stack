from __future__ import annotations

from dataclasses import dataclass

from tools.recorder import NDJSONRecorder, recorder
from tools.rules import Rules, rules

from .state import AlertDeduper, Stats, deduper, stats
from .ws import WSHub, hub


@dataclass
class Services:
    stats: Stats
    deduper: AlertDeduper
    hub: WSHub
    recorder: NDJSONRecorder
    rules: Rules


_services = Services(
    stats=stats,
    deduper=deduper,
    hub=hub,
    recorder=recorder,
    rules=rules,
)


def get_services() -> Services:
    return _services


def set_services(services: Services) -> None:
    global _services
    _services = services


__all__ = ['Services', 'get_services', 'set_services']
