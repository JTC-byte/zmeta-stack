from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from schemas.zmeta import ZMeta
from tools.ingest_adapters import adapt_to_zmeta

from .json_utils import dumps
from .services import Services, get_services

log = logging.getLogger('zmeta.ingest')


def _services(services: Services | None) -> Services:
    return services or get_services()


def validate_or_adapt(payload: dict, services: Services | None = None) -> ZMeta:
    svc = _services(services)
    stats = svc.stats
    adapter_name = 'native'
    try:
        zmeta_obj = ZMeta.model_validate(payload)
    except ValidationError:
        adapted = adapt_to_zmeta(payload)
        if adapted is None:
            raise
        adapter_name, adapted_payload = adapted
        zmeta_obj = ZMeta.model_validate(adapted_payload)
    else:
        adapter_name = 'native'

    if zmeta_obj.sequence is None:
        zmeta_obj = zmeta_obj.model_copy(update={'sequence': stats.next_sequence()})

    stats.note_adapter(adapter_name)
    return zmeta_obj


async def dispatch_zmeta(z: ZMeta, *, context: str, services: Services | None = None) -> None:
    svc = _services(services)
    data_json = z.model_dump_json()
    data_dict = z.model_dump()
    await svc.hub.broadcast_text(data_json)
    await svc.recorder.enqueue(data_json)
    svc.stats.note_validated()

    try:
        alerts = svc.rules.apply(data_dict)
    except Exception:
        log.exception('rules.apply failed (%s)', context)
        return

    await publish_alerts(alerts, services=svc)


async def publish_alerts(alerts: list[dict[str, Any]], services: Services | None = None) -> None:
    svc = _services(services)
    for alert in alerts:
        if svc.deduper.should_send(alert):
            await svc.hub.broadcast_text(dumps(alert))
            svc.stats.note_alert()


async def ingest_payload(payload: dict, *, context: str, services: Services | None = None) -> ZMeta:
    svc = _services(services)
    zmeta_obj = validate_or_adapt(payload, services=svc)
    await dispatch_zmeta(zmeta_obj, context=context, services=svc)
    return zmeta_obj


__all__ = [
    'dispatch_zmeta',
    'ingest_payload',
    'publish_alerts',
    'validate_or_adapt',
]
