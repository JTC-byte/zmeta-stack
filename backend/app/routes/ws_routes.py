from __future__ import annotations

from typing import Callable, Optional

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ..config import WS_GREETING
from ..dependencies import (
    get_auth_enabled,
    get_auth_header,
    get_secret_verifier,
    get_ws_hub,
)
from ..ws import WSHub

log = structlog.get_logger("zmeta.ws")

router = APIRouter()


@router.websocket('/ws')
async def websocket_endpoint(
    websocket: WebSocket,
    hub: WSHub = Depends(get_ws_hub),
    auth_enabled: bool = Depends(get_auth_enabled),
    auth_header: str = Depends(get_auth_header),
    verify_secret: Callable[[Optional[str]], bool] = Depends(get_secret_verifier),
):
    provided = websocket.headers.get(auth_header) or websocket.query_params.get('secret')
    if auth_enabled and not verify_secret(provided):
        await websocket.close(code=4401)
        return

    await hub.connect(websocket)
    await websocket.send_text(WS_GREETING)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f'Echo: {data}')
    except WebSocketDisconnect:
        client = getattr(websocket, 'client', None)
        log.debug("WebSocket disconnected", client=client)
    except Exception:
        client = getattr(websocket, 'client', None)
        log.exception("Unhandled websocket error", client=client)
    finally:
        await hub.disconnect(websocket)


__all__ = ['router']
