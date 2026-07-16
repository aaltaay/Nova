"""Push scanner table price patches to connected WebSocket clients."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import scanner_tab_registry as _tabs

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
        _tabs.clear(ws)


@router.websocket("/ws/scanner")
async def ws_scanner(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    try:
        await websocket.send_text(json.dumps({
            "type": "subscribed",
            "tab": "none",
        }))
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw) if raw else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "set_active_tab":
                tab = _tabs.set_tab(websocket, str(msg.get("tab") or "none"))
                await websocket.send_text(json.dumps({
                    "type": "subscription_state",
                    "tab": tab,
                    "dominant_tab": _tabs.get_dominant_tab(),
                }))
    except WebSocketDisconnect:
        logger.debug("scanner WS client disconnected")
    except Exception as exc:
        logger.debug("scanner WS closed: %s", exc)
    finally:
        _clients.discard(websocket)
        _tabs.clear(websocket)
