"""
IBKR trading routes — thin handlers that delegate to ibkr/*.py modules.

Endpoints:
  GET  /api/ibkr/status           -- connection state + mode (paper/live/disconnected)
  GET  /api/ibkr/account          -- account summary
  GET  /api/ibkr/positions        -- portfolio / positions
  GET  /api/ibkr/orders           -- open orders
  POST /api/ibkr/order            -- place market or limit order
  DELETE /api/ibkr/order/{id}     -- cancel order
  POST /api/ibkr/depth/subscribe  -- subscribe to L2 depth for a symbol
  POST /api/ibkr/depth/unsubscribe -- unsubscribe symbol
  GET  /api/ibkr/depth            -- list currently subscribed depth symbols
  WS   /ws/ibkr/depth/{symbol}    -- streaming Level 2 book updates
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ibkr import client as _client
from ibkr import depth as _depth
from ibkr import orders as _orders
from ibkr import account as _account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ibkr", tags=["ibkr"])
ws_router = APIRouter(tags=["ibkr-ws"])


# ── Status ─────────────────────────────────────────────────────────────────────

@router.get("/status")
async def ibkr_status() -> dict:
    return {
        "enabled": _client.is_enabled(),
        "connected": _client.is_connected(),
        "mode": _client.account_mode(),
    }


# ── Account ────────────────────────────────────────────────────────────────────

@router.get("/account")
async def ibkr_account() -> dict:
    return _account.get_account_summary()


@router.get("/positions")
async def ibkr_positions() -> list:
    return _account.get_portfolio()


@router.get("/orders")
async def ibkr_open_orders() -> list:
    return _orders.open_orders()


# ── Orders ────────────────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    symbol: str
    side: str           # "BUY" | "SELL"
    qty: float
    order_type: str = "MKT"   # "MKT" | "LMT"
    limit_price: float | None = None


@router.post("/order")
async def place_order(req: OrderRequest) -> dict:
    return _orders.place_order(
        symbol=req.symbol.upper(),
        side=req.side.upper(),  # type: ignore[arg-type]
        qty=req.qty,
        order_type=req.order_type.upper(),  # type: ignore[arg-type]
        limit_price=req.limit_price,
    )


@router.delete("/order/{order_id}")
async def cancel_order(order_id: int) -> dict:
    return _orders.cancel_order(order_id)


# ── Depth ─────────────────────────────────────────────────────────────────────

class DepthSubscribeRequest(BaseModel):
    symbol: str


@router.post("/depth/subscribe")
async def depth_subscribe(req: DepthSubscribeRequest) -> dict:
    symbol = req.symbol.upper()
    result = _depth.subscribe(symbol)
    if result.get("ok"):
        # Continuous local L2 + tape recorder while DepthLadder is open.
        from l2 import continuous as _l2_continuous
        try:
            _l2_continuous.start(symbol)
        except Exception:
            logger.exception("l2.continuous: failed to start for %s", symbol)
    return result


@router.post("/depth/unsubscribe")
async def depth_unsubscribe(req: DepthSubscribeRequest) -> None:
    symbol = req.symbol.upper()
    from l2 import continuous as _l2_continuous
    try:
        await _l2_continuous.stop(symbol)
    except Exception:
        logger.exception("l2.continuous: failed to stop for %s", symbol)
    _depth.unsubscribe(symbol)


@router.get("/depth")
async def depth_list() -> dict:
    return {"symbols": _depth.subscribed_symbols()}


# ── Depth WebSocket ────────────────────────────────────────────────────────────

@ws_router.websocket("/ws/ibkr/depth/{symbol}")
async def ws_depth(websocket: WebSocket, symbol: str) -> None:
    symbol = symbol.upper()
    await websocket.accept()

    # Auto-subscribe if not already
    if symbol not in _depth.subscribed_symbols():
        result = _depth.subscribe(symbol)
        if not result["ok"]:
            await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
            await websocket.close()
            return

    from l2 import continuous as _l2_continuous
    try:
        _l2_continuous.start(symbol)
    except Exception:
        logger.exception("l2.continuous: failed to start for WS %s", symbol)

    await websocket.send_text(json.dumps({"type": "subscribed", "symbol": symbol}))

    try:
        async for book in _depth.stream(symbol):
            if book is None:
                # Heartbeat timeout
                await websocket.send_text(json.dumps({"type": "ping"}))
            else:
                await websocket.send_text(json.dumps({"type": "book", "symbol": symbol, "data": book}))
    except WebSocketDisconnect:
        logger.debug("IBKR depth WS disconnected: %s", symbol)
    except Exception as exc:
        logger.error("IBKR depth WS error for %s: %s", symbol, exc)
    finally:
        try:
            await _l2_continuous.stop(symbol)
        except Exception:
            logger.exception("l2.continuous: failed to stop for WS %s", symbol)
