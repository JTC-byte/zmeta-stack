from __future__ import annotations

from dataclasses import dataclass

from tools.recorder import NDJSONRecorder, recorder
from tools.rules import Rules, rules

from .metrics import MetricsProvider, metrics
from .state import AlertDeduper, deduper
from .ws import WSHub, hub


@dataclass
class Services:
    metrics: MetricsProvider
    deduper: AlertDeduper
    hub: WSHub
    recorder: NDJSONRecorder
    rules: Rules


def get_services() -> Services:
    """Return the default service bundle wired to the app singletons."""

    return Services(
        metrics=metrics,
        deduper=deduper,
        hub=hub,
        recorder=recorder,
        rules=rules,
    )


__all__ = ['Services', 'get_services']
