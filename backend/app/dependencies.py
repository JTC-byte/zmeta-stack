from __future__ import annotations

from typing import Annotated, Callable, Optional

from fastapi import Depends

from tools.recorder import NDJSONRecorder
from tools.rules import Rules

from .config import AUTH_HEADER, auth_enabled, verify_shared_secret
from .metrics import MetricsProvider
from .services import Services, get_services
from .state import AlertDeduper
from .ws import WSHub


ServicesDep = Annotated[Services, Depends(get_services)]


def get_metrics(services: ServicesDep) -> MetricsProvider:
    return services.metrics


MetricsDep = Annotated[MetricsProvider, Depends(get_metrics)]

# Backwards-compatible alias until callers migrate to the metrics terminology.
get_stats = get_metrics


def get_ws_hub(services: ServicesDep) -> WSHub:
    return services.hub


def get_deduper(services: ServicesDep) -> AlertDeduper:
    return services.deduper


def get_recorder(services: ServicesDep) -> NDJSONRecorder:
    return services.recorder


def get_rules(services: ServicesDep) -> Rules:
    return services.rules


def get_auth_enabled() -> bool:
    return auth_enabled()


def get_auth_header() -> str:
    return AUTH_HEADER


def get_secret_verifier() -> Callable[[Optional[str]], bool]:
    return verify_shared_secret


__all__ = [
    'MetricsDep',
    'ServicesDep',
    'get_auth_enabled',
    'get_auth_header',
    'get_deduper',
    'get_metrics',
    'get_recorder',
    'get_rules',
    'get_secret_verifier',
    'get_stats',
    'get_ws_hub',
]
