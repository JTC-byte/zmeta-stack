from __future__ import annotations

from typing import Callable, Optional

from fastapi import Depends

from tools.recorder import NDJSONRecorder
from tools.rules import Rules

from .config import AUTH_HEADER, auth_enabled, verify_shared_secret
from .services import Services, get_services
from .state import AlertDeduper, Stats
from .ws import WSHub


def get_stats(services: Services = Depends(get_services)) -> Stats:
    return services.stats


def get_ws_hub(services: Services = Depends(get_services)) -> WSHub:
    return services.hub


def get_deduper(services: Services = Depends(get_services)) -> AlertDeduper:
    return services.deduper


def get_recorder(services: Services = Depends(get_services)) -> NDJSONRecorder:
    return services.recorder


def get_rules(services: Services = Depends(get_services)) -> Rules:
    return services.rules


def get_auth_enabled() -> bool:
    return auth_enabled()


def get_auth_header() -> str:
    return AUTH_HEADER


def get_secret_verifier() -> Callable[[Optional[str]], bool]:
    return verify_shared_secret


__all__ = [
    'get_auth_enabled',
    'get_auth_header',
    'get_deduper',
    'get_recorder',
    'get_rules',
    'get_secret_verifier',
    'get_stats',
    'get_ws_hub',
]
