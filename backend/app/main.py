# backend/app/main.py
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from schemas.zmeta import ZMeta
from tools.recorder import recorder
from tools.rules import rules

from .config import (
    ALLOWED_ORIGINS,
    APP_TITLE,
    auth_enabled,
    ui_url,
    verify_shared_secret,
)
from .ingest import ingest_payload as _ingest_payload
from .ingest import validate_or_adapt as _validate_or_adapt
from .json_utils import dumps as _dumps
from .lifespan import app_lifespan
from .routes import api_v1, root_router, ws_router
from .state import AlertDeduper, deduper, stats
from .ws import hub

log = logging.getLogger('zmeta')

_app_title = APP_TITLE

_auth_enabled = auth_enabled
_verify_shared_secret = verify_shared_secret
_ui_url = ui_url

app = FastAPI(title=_app_title, lifespan=app_lifespan)

app.mount('/ui', StaticFiles(directory='zmeta_map_dashboard', html=True), name='ui')
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=['GET', 'POST'],
    allow_headers=['*'],
)

app.include_router(root_router)
app.include_router(api_v1)
app.include_router(ws_router)

__all__ = [
    'ZMeta',
    'AlertDeduper',
    '_auth_enabled',
    '_dumps',
    '_ingest_payload',
    '_ui_url',
    '_validate_or_adapt',
    'app',
    'deduper',
    'hub',
    'recorder',
    'log',
    'rules',
    'stats',
]
