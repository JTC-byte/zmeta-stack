from fastapi import APIRouter

from .core import router as core_router
from .ingest_http import router as ingest_router
from .root import router as root_router
from .rules import router as rules_router
from .ws_routes import router as ws_router

api_v1 = APIRouter(prefix='/api/v1')
api_v1.include_router(core_router)
api_v1.include_router(rules_router)
api_v1.include_router(ingest_router)

__all__ = ['api_v1', 'root_router', 'ws_router']
