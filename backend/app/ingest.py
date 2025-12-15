from __future__ import annotations

from typing import Any

import structlog
from pydantic import ValidationError

from schemas.zmeta import ZMeta, parse_zmeta
from tools.ingest_adapters import adapt_to_zmeta

from .json_utils import dumps
from .services import Services, get_services

log = structlog.get_logger("zmeta.ingest")


def resolve_services(services: Services | None = None) -> Services:
    """Return the provided service bundle or fall back to the defaults."""

    return services if services is not None else get_services()


def validate_or_adapt(payload: dict, services: Services | None = None) -> ZMeta:
    svc = resolve_services(services)
    metrics = svc.metrics
    adapter_name = "native"
    try:
        zmeta_obj = parse_zmeta(payload)
    except ValidationError:
        adapted = adapt_to_zmeta(payload)
        if adapted is None:
            raise
        adapter_name, adapted_payload = adapted
        zmeta_obj = parse_zmeta(adapted_payload)

    if zmeta_obj.sequence is None:
        zmeta_obj = zmeta_obj.model_copy(update={"sequence": metrics.next_sequence()})

    metrics.note_adapter(adapter_name)
    return zmeta_obj


async def dispatch_zmeta(z: ZMeta, *, context: str, services: Services | None = None) -> None:
    svc = resolve_services(services)
    data_json = z.model_dump_json()
    data_dict = z.model_dump()
    await svc.hub.broadcast_text(data_json)
    await svc.recorder.enqueue(data_json)
    svc.metrics.note_validated()

    try:
        alerts = svc.rules.apply(data_dict)
    except Exception:
        log.exception("rules.apply failed", context=context)
        return

    await publish_alerts(alerts, services=svc)


async def publish_alerts(alerts: list[dict[str, Any]], services: Services | None = None) -> None:
    svc = resolve_services(services)
    for alert in alerts:
        if svc.deduper.should_send(alert):
            await svc.hub.broadcast_text(dumps(alert))
            svc.metrics.note_alert()


async def ingest_payload(payload: dict, *, context: str, services: Services | None = None) -> ZMeta:
    svc = resolve_services(services)
    zmeta_obj = validate_or_adapt(payload, services=svc)
    await dispatch_zmeta(zmeta_obj, context=context, services=svc)
    return zmeta_obj


__all__ = [
    "dispatch_zmeta",
    "ingest_payload",
    "publish_alerts",
    "resolve_services",
    "validate_or_adapt",
]
