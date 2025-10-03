from __future__ import annotations

import time
from typing import Dict

from fastapi import APIRouter, Depends

from schemas.zmeta import SUPPORTED_SCHEMA_VERSIONS

from ..config import (
    ALLOWED_ORIGINS,
    APP_TITLE,
    AUTH_HEADER,
    ENVIRONMENT,
    WS_QUEUE_MAX,
)
from ..dependencies import get_auth_enabled, get_stats, get_ws_hub
from ..state import Stats
from ..ws import WSHub

router = APIRouter()


@router.get('/status')
def api_status(hub: WSHub = Depends(get_ws_hub)) -> Dict[str, object]:
    return {'status': f'{APP_TITLE} running', 'clients': len(hub.clients)}


@router.get('/healthz')
async def healthz(
    stats: Stats = Depends(get_stats),
    hub: WSHub = Depends(get_ws_hub),
    auth_enabled: bool = Depends(get_auth_enabled),
) -> Dict[str, object]:
    age = None if stats.last_packet_ts is None else round(max(0.0, time.time() - stats.last_packet_ts), 2)
    return {
        'status': 'ok',
        'clients': len(hub.clients),
        'udp_received_total': stats.udp_received_total,
        'validated_total': stats.validated_total,
        'dropped_total': stats.dropped_total,
        'alerts_total': stats.alerts_total,
        'eps_1s': stats.eps(1),
        'eps_10s': stats.eps(10),
        'last_packet_age_s': age,
        'ws_queue_max': WS_QUEUE_MAX,
        'ws_sent_total': stats.ws_sent_total,
        'ws_dropped_total': stats.ws_dropped_total,
        'auth_mode': 'shared_secret' if auth_enabled else 'disabled',
        'auth_header': AUTH_HEADER if auth_enabled else None,
        'allowed_origins': ALLOWED_ORIGINS,
        'environment': ENVIRONMENT,
        'supported_schema_versions': sorted(SUPPORTED_SCHEMA_VERSIONS),
    }


__all__ = ['router']
