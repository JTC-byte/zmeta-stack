from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from ..dependencies import get_auth_enabled, get_auth_header, get_secret_verifier
from ..ingest import ingest_payload
from ..ws import hub

router = APIRouter()


@router.post('/ingest')
async def ingest(
    request: Request,
    payload: dict[str, Any],
    auth_enabled: bool = Depends(get_auth_enabled),
    auth_header: str = Depends(get_auth_header),
    verify_secret: Callable[[Optional[str]], bool] = Depends(get_secret_verifier),
):
    if auth_enabled:
        provided = request.headers.get(auth_header) or request.query_params.get('secret')
        if not verify_secret(provided):
            raise HTTPException(status_code=401, detail='Unauthorized')

    try:
        await ingest_payload(payload, context='http')
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    return {'ok': True, 'broadcast_to': len(hub.clients)}


__all__ = ['router']


