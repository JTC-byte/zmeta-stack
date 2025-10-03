from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get('/', include_in_schema=False)
def home_redirect():
    return RedirectResponse(url='/ui/live_map.html', status_code=307)


@router.get('/favicon.ico', include_in_schema=False)
async def favicon_redirect():
    return RedirectResponse(url='/ui/favicon.svg')


@router.get('/api', include_in_schema=False)
def legacy_api_status():
    return RedirectResponse(url='/api/v1/status', status_code=307)


@router.get('/healthz', include_in_schema=False)
async def legacy_health():
    return RedirectResponse(url='/api/v1/healthz', status_code=307)


__all__ = ['router']
