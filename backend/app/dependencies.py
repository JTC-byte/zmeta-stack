from __future__ import annotations

from typing import Callable, Optional

from tools.recorder import NDJSONRecorder, recorder
from tools.rules import rules

from .config import AUTH_HEADER, auth_enabled, verify_shared_secret
from .state import AlertDeduper, Stats, deduper, stats
from .ws import WSHub, hub


def get_stats() -> Stats:
    return stats


def get_ws_hub() -> WSHub:
    return hub


def get_deduper() -> AlertDeduper:
    return deduper


def get_recorder() -> NDJSONRecorder:
    return recorder


def get_rules():
    return rules


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
