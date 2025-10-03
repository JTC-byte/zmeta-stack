from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from schemas.zmeta import ZMeta
from tools.ingest_adapters import adapt_to_zmeta
from tools.recorder import recorder
from tools.rules import rules

from .json_utils import dumps
from .state import deduper, stats
from .ws import hub

log = logging.getLogger('zmeta.ingest')


def validate_or_adapt(payload: dict) -> ZMeta:
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


async def dispatch_zmeta(z: ZMeta, *, context: str) -> None:
    data_json = z.model_dump_json()
    data_dict = z.model_dump()
    await hub.broadcast_text(data_json)
    await recorder.enqueue(data_json)
    stats.note_validated()

    try:
        alerts = rules.apply(data_dict)
    except Exception:
        log.exception('rules.apply failed (%s)', context)
        return

    await publish_alerts(alerts)


async def publish_alerts(alerts: list[dict[str, Any]]) -> None:
    for alert in alerts:
        if deduper.should_send(alert):
            await hub.broadcast_text(dumps(alert))
            stats.note_alert()


async def ingest_payload(payload: dict, *, context: str) -> ZMeta:
    zmeta_obj = validate_or_adapt(payload)
    await dispatch_zmeta(zmeta_obj, context=context)
    return zmeta_obj


__all__ = [
    'dispatch_zmeta',
    'ingest_payload',
    'publish_alerts',
    'validate_or_adapt',
]
