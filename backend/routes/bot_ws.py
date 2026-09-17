"""Bot Eyes + audit WebSockets. Same L1/L2 surfaces as the UI."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from bot.audit import list_entries, subscribe, unsubscribe
from bot.focus import snapshot as focus_snapshot
from bot.persist import load_session
from bot.quotes import eyes_row
from constants_bot import BOT_EYES_PUSH_SEC, BOT_LEVEL_OFF, BOT_LOOPBACK_HOSTS

ws_router = APIRouter(tags=["bot-ws"])


def _loopback(websocket: WebSocket) -> bool:
    host = ""
    if websocket.client is not None:
        host = (websocket.client.host or "").strip().lower()
    return host in BOT_LOOPBACK_HOSTS or host.startswith("127.")


@ws_router.websocket("/ws/bot/eyes")
async def bot_eyes(websocket: WebSocket) -> None:
    await websocket.accept()
    if not _loopback(websocket):
        await websocket.send_json({"type": "error", "reason": "BOT_NOT_LOOPBACK"})
        await websocket.close()
        return
    try:
        while True:
            row = load_session()
            level = int(row.get("level") or BOT_LEVEL_OFF)
            if level <= BOT_LEVEL_OFF:
                await websocket.send_json({"type": "dark", "level": 0})
                await asyncio.sleep(BOT_EYES_PUSH_SEC)
                continue
            focus = focus_snapshot()
            symbols = list(dict.fromkeys(list(focus.get("focus") or []) + list(focus.get("trader_live") or [])))
            quotes = [eyes_row(sym) for sym in symbols]
            await websocket.send_json({
                "type": "eyes",
                "level": level,
                "focus": focus,
                "quotes": quotes,
            })
            await asyncio.sleep(BOT_EYES_PUSH_SEC)
    except WebSocketDisconnect:
        return


@ws_router.websocket("/ws/bot/audit")
async def bot_audit_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    if not _loopback(websocket):
        await websocket.send_json({"type": "error", "reason": "BOT_NOT_LOOPBACK"})
        await websocket.close()
        return
    await websocket.send_json({"type": "snapshot", "entries": list_entries(limit=50)})
    queue = subscribe()
    try:
        while True:
            try:
                entry = await asyncio.wait_for(queue.get(), timeout=20)
            except TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue
            await websocket.send_json({"type": "audit", "entry": entry})
    except WebSocketDisconnect:
        return
    finally:
        unsubscribe(queue)
