"""Push scanner table price patches to connected WebSocket clients."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()
_clients: set[WebSocket] = set()


async def broadcast(payload: dict[str, Any]) -> None:
    """Send a price_patch or price_heartbeat to every /ws/scanner client."""
    if not _clients:
        return
    text = json.dumps(payload)
    dead: list[WebSocket] = []
    for ws in list(_clients):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


@router.websocket("/ws/scanner")
async def ws_scanner(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    try:
        await websocket.send_text(json.dumps({"type": "subscribed"}))
        while True:
            # Keep the socket open; client may send pings — ignore payload.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("scanner WS closed: %s", exc)
    finally:
        _clients.discard(websocket)
