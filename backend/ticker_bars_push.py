"""Push chart bar fills to ticker-detail WebSocket clients."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def broadcast_bars_patch(symbol: str, payload: dict[str, Any]) -> None:
    """Send ``bars_patch`` to clients watching ``symbol``. IB-loop safe."""
    symbol = symbol.upper()
    msg = {
        "type": "bars_patch",
        "symbol": symbol,
        "timeframe": payload.get("timeframe"),
        "bars": payload.get("bars") or [],
        "coverage": payload.get("coverage"),
        "source": payload.get("source", "ibkr"),
    }
    try:
        from ibkr.loop_supervisor import is_ib_loop, publish_to_http

        if is_ib_loop():
            publish_to_http(_enqueue, symbol, msg)
            return
    except Exception:
        logger.debug("bars_patch: loop hop skipped for %s", symbol)
    _enqueue(symbol, msg)


def _enqueue(symbol: str, msg: dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_send(symbol, msg), name=f"bars_patch.{symbol}")


async def _send(symbol: str, msg: dict[str, Any]) -> None:
    from ticker import _ticker_ws_clients

    clients = _ticker_ws_clients.get(symbol)
    if not clients:
        return
    text = json.dumps(msg)
    dead = []
    for ws in list(clients):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)
