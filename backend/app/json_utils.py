from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        try:
            if isinstance(value, datetime) and value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            iso = value.isoformat()
            return iso.replace('+00:00', 'Z')
        except Exception:
            return str(value)
    return str(value)


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=json_default, separators=(',', ':'), ensure_ascii=False)
