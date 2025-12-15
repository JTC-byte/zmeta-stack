from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends

from ..config import (
    ALLOWED_ORIGINS,
    APP_TITLE,
    AUTH_HEADER,
    ENVIRONMENT,
    WS_QUEUE_MAX,
)
from ..dependencies import get_auth_enabled, get_metrics, get_ws_hub
from ..metrics import MetricsProvider
from ..ws import WSHub

status_router = APIRouter(prefix='/status', tags=['status'])
health_router = APIRouter(prefix='/healthz', tags=['status'])


@status_router.get('')
def api_status(
    hub: WSHub = Depends(get_ws_hub),
    metrics: MetricsProvider = Depends(get_metrics),
) -> Dict[str, object]:
    snapshot = metrics.snapshot()
    ws_stats = hub.stats()
    return {
        'status': f'{APP_TITLE} running',
        'clients': ws_stats['clients_total'],
        'adapter_counts': snapshot.adapter_counts,
        'udp_received_total': snapshot.udp_received_total,
        'validated_total': snapshot.validated_total,
        'ws': ws_stats,
    }


@health_router.get('')
async def healthz(
    metrics: MetricsProvider = Depends(get_metrics),
    hub: WSHub = Depends(get_ws_hub),
    auth_enabled: bool = Depends(get_auth_enabled),
) -> Dict[str, object]:
    snapshot = metrics.snapshot()
    ws_stats = hub.stats()
    return {
        'status': 'ok',
        'clients': len(hub.clients),
        'udp_received_total': snapshot.udp_received_total,
        'validated_total': snapshot.validated_total,
        'dropped_total': snapshot.dropped_total,
        'alerts_total': snapshot.alerts_total,
        'eps_1s': metrics.eps(1),
        'eps_10s': metrics.eps(10),
        'last_packet_age_s': metrics.last_packet_age(),
        'ws_queue_max': WS_QUEUE_MAX,
        'ws_sent_total': snapshot.ws_sent_total,
        'ws_dropped_total': snapshot.ws_dropped_total,
        'adapter_counts': snapshot.adapter_counts,
        'ws': ws_stats,
        'auth_mode': 'shared_secret' if auth_enabled else 'disabled',
        'auth_header': AUTH_HEADER if auth_enabled else None,
        'allowed_origins': ALLOWED_ORIGINS,
        'environment': ENVIRONMENT,
    }


__all__ = ['status_router', 'health_router']
