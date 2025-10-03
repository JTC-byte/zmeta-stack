from __future__ import annotations

import os
from typing import List

from dotenv import load_dotenv

load_dotenv()

APP_TITLE = 'ZMeta Backend'


def _env_csv(name: str, default: List[str]) -> List[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(',') if item.strip()]


UDP_HOST = os.getenv('ZMETA_UDP_HOST', '0.0.0.0')
UDP_PORT = int(os.getenv('ZMETA_UDP_PORT', '5005'))
UDP_QUEUE_MAX = int(os.getenv('ZMETA_UDP_QUEUE_MAX', '4096'))
UI_BASE_URL = os.getenv('ZMETA_UI_BASE_URL', 'http://127.0.0.1:8000')
WS_GREETING = os.getenv('ZMETA_WS_GREETING', 'Connected to ZMeta WebSocket')
ALLOWED_ORIGINS = _env_csv('ZMETA_CORS_ORIGINS', ['*'])
AUTH_HEADER = os.getenv('ZMETA_AUTH_HEADER', 'x-zmeta-secret')
SHARED_SECRET = os.getenv('ZMETA_SHARED_SECRET', '').strip()
ENVIRONMENT = os.getenv('ZMETA_ENV', 'dev')
WS_QUEUE_MAX = int(os.getenv('ZMETA_WS_QUEUE', '64'))


def auth_enabled() -> bool:
    return bool(SHARED_SECRET)


def verify_shared_secret(provided: str | None) -> bool:
    if not auth_enabled():
        return True
    return provided == SHARED_SECRET


def ui_url(path: str) -> str:
    base = UI_BASE_URL.rstrip('/')
    return f'{base}{path}'
