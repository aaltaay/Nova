"""
IBKR trading routes — thin handlers that delegate to ibkr/*.py modules.

Endpoints:
  GET  /api/ibkr/status           -- connection state + mode (paper/live/disconnected)
  POST /api/ibkr/reconnect        -- reload .env + reconnect to configured port
  POST /api/ibkr/gateway-mode     -- user-initiated Paper<->Live port switch (no spend unlock)
  POST /api/ibkr/launch-gateway  -- start/focus IB Gateway (user-initiated, Windows)
  GET  /api/ibkr/account          -- account summary
  GET  /api/ibkr/positions        -- portfolio / positions
  GET  /api/ibkr/orders           -- open / working orders
  GET  /api/ibkr/orders/closed    -- filled / cancelled session orders (WID-027)
  POST /api/ibkr/order            -- place market, limit, or stop order
  DELETE /api/ibkr/order/{id}     -- cancel order
  POST /api/ibkr/depth/subscribe  -- subscribe to L2 depth for a symbol
  POST /api/ibkr/depth/unsubscribe -- unsubscribe symbol
  GET  /api/ibkr/depth            -- list currently subscribed depth symbols
  WS   /ws/ibkr/depth/{symbol}    -- streaming Level 2 book updates
  WS   /ws/ibkr/tape/{symbol}     -- streaming Time & Sales (AllLast tick-by-tick)
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ibkr import client as _client
from ibkr import depth as _depth
from ibkr import orders as _orders
from ibkr import account as _account
from ibkr import tape_stream as _tape
from ibkr.errors import IbkrAccountError
from routes.trading_execution import router as execution_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ibkr", tags=["ibkr"])
router.include_router(execution_router)
ws_router = APIRouter(tags=["ibkr-ws"])


# ── Status ─────────────────────────────────────────────────────────────────────

@router.get("/status")
async def ibkr_status() -> dict:
    snap = _client_safety_status()
    from ibkr import gateway_heal as _heal
    from ibkr import port_diagnostics as _ports

    connected = _client.is_connected()
    return {
        "enabled": _client.is_enabled(),
        "connected": connected,
        "mode": _client.account_mode(),
        "broker_account_kind": _client.broker_account_kind(),
        **snap,
        **_heal.heal_status(),
        **_ports.status_port_fields(connected=connected),
    }


@router.post("/reconnect")
async def ibkr_reconnect() -> dict:
    """Reload .env (override) and reconnect to the configured Gateway port."""
    return await _client.force_reconnect()


class GatewayModeRequest(BaseModel):
    mode: str  # "paper" | "live"


@router.post("/gateway-mode")
async def ibkr_gateway_mode(body: GatewayModeRequest) -> dict:
    """User-initiated Paper↔Live switch — persists + reconnects; never unlocks spend."""
    mode = (body.mode or "").strip().lower()
    if mode not in ("paper", "live"):
        raise HTTPException(status_code=400, detail=f"invalid mode {body.mode!r} (must be paper or live)")
    return await _client.request_gateway_mode(mode)


@router.post("/launch-gateway")
async def ibkr_launch_gateway() -> dict:
    """Start IB Gateway (or focus it) on this machine — does not place orders."""
    from ibkr.launch_gateway import launch_or_focus_gateway

    return launch_or_focus_gateway()


def _client_safety_status() -> dict:
    from ibkr import safety as _safety
    return _safety.status_snapshot()


# ── Account ────────────────────────────────────────────────────────────────────

@router.get("/account")
async def ibkr_account() -> dict:
    # Async refresh avoids "event loop is already running" from sync IB waits.
    try:
        return await _account.refresh_account_summary()
    except IbkrAccountError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/positions")
async def ibkr_positions() -> list:
    # Qty from positions()/long_qty SSOT; MTM/PnL joined from portfolio.
    try:
        return _account.positions_for_ui()
    except IbkrAccountError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/orders")
async def ibkr_open_orders() -> list:
    try:
        return _orders.open_orders()
    except IbkrAccountError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/orders/closed")
async def ibkr_closed_orders(limit: int | None = None) -> list:
    """Filled / cancelled / failed session orders (Webull History / Closed)."""
    try:
        return await _orders.closed_orders_async(limit=limit)
    except IbkrAccountError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ── Depth ─────────────────────────────────────────────────────────────────────

class DepthSubscribeRequest(BaseModel):
    symbol: str


@router.post("/depth/subscribe")
async def depth_subscribe(req: DepthSubscribeRequest) -> dict:
    symbol = req.symbol.upper()
    result = await _depth.subscribe_async(symbol)
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

    from l2 import continuous as _l2_continuous

    # Auto-subscribe if not already
    if symbol not in _depth.subscribed_symbols():
        result = await _depth.subscribe_async(symbol)
        if not result["ok"]:
            await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
            await websocket.close()
            return

    try:
        _l2_continuous.start(symbol)
    except Exception:
        logger.exception("l2.continuous: failed to start for WS %s", symbol)

    # Everything from here on must be inside the try/finally: if the client
    # disconnects before the first send_text() completes (React effect
    # double-invoke, rapid symbol switching), send_text() itself raises
    # WebSocketDisconnect. That used to happen *before* ws_viewer_opened() was
    # paired with a matching close, permanently inflating the viewer count and
    # defeating cleanup (see PROBLEM_LOG 2026-07-13, "Level 2 depth line leak").
    viewer_opened = False
    try:
        _depth.ws_viewer_opened(symbol)
        viewer_opened = True

        # Remount race: a previous viewer's cleanup may have dropped the line
        # between our initial subscribe check and viewer_opened. Re-subscribe
        # before streaming so stream() does not exit immediately on a missing queue.
        if not _depth.has_queue(symbol):
            result = await _depth.subscribe_async(symbol)
            if not result["ok"]:
                await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
                return
            try:
                _l2_continuous.start(symbol)
            except Exception:
                logger.exception("l2.continuous: failed to restart for WS %s", symbol)

        await websocket.send_text(json.dumps({"type": "subscribed", "symbol": symbol}))

        # A symbol already subscribed by another viewer (or a fresh page
        # reload re-attaching to a still-open depth line) needs today's
        # snapshot right away — see should_send_current_book().
        current = _depth.current_book(symbol)
        if _depth.should_send_current_book(current):
            await websocket.send_text(json.dumps({"type": "book", "symbol": symbol, "data": current}))

        async for book in _depth.stream(symbol):
            if book is None:
                # Heartbeat timeout
                await websocket.send_text(json.dumps({"type": "ping"}))
            else:
                await websocket.send_text(json.dumps({"type": "book", "symbol": symbol, "data": book}))
    except WebSocketDisconnect:
        logger.debug("IBKR depth WS disconnected: %s", symbol)
    except Exception as exc:
        logger.exception("IBKR depth WS error for %s: %s", symbol, exc)
    finally:
        # Release only once the LAST viewer is gone — and only after a short
        # grace window so React StrictMode / DepthLadder reconnects can
        # reattach without tearing down reqMktDepth (Connecting-depth flicker).
        # continuous.stop belongs here too: stopping it on every viewer close
        # killed recording for any remaining viewers of the same symbol.
        if viewer_opened and _depth.ws_viewer_closed(symbol):
            idle = await _depth.release_when_idle(symbol)
            if idle:
                try:
                    await _l2_continuous.stop(symbol)
                except Exception:
                    logger.exception("l2.continuous: failed to stop for WS %s", symbol)
                from l2 import recorder as _l2_recorder
                if not _l2_recorder.is_recording(symbol):
                    _depth.unsubscribe(symbol)


# ── Time & Sales WebSocket ─────────────────────────────────────────────────────

@ws_router.websocket("/ws/ibkr/tape/{symbol}")
async def ws_tape(websocket: WebSocket, symbol: str) -> None:
    """Stream IBKR AllLast tick-by-tick Time & Sales prints for a symbol.

    Auto-subscribes on first viewer, refcounts concurrent viewers, and
    unsubscribes when the last viewer disconnects — same lifecycle as depth.
    Symbol gates applied on every message (msg.symbol == requested symbol).
    """
    symbol = symbol.upper()
    await websocket.accept()

    if not _client.is_connected():
        await websocket.send_text(json.dumps({"type": "error", "message": "IBKR not connected"}))
        await websocket.close()
        return

    if not _tape.has_queue(symbol):
        result = await _tape.subscribe_async(symbol)
        if not result["ok"]:
            await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
            await websocket.close()
            return

    viewer_opened = False
    try:
        _tape.ws_viewer_opened(symbol)
        viewer_opened = True

        # Remount race: previous viewer cleanup may have dropped the queue.
        if not _tape.has_queue(symbol):
            result = await _tape.subscribe_async(symbol)
            if not result["ok"]:
                await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
                return

        await websocket.send_text(json.dumps({"type": "subscribed", "symbol": symbol}))

        async for print_data in _tape.stream(symbol):
            if print_data is None:
                await websocket.send_text(json.dumps({"type": "ping", "symbol": symbol}))
                continue
            if print_data.get("symbol") != symbol:
                continue
            msg_type = print_data.get("type") or "print"
            if msg_type == "error":
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "symbol": symbol,
                            "message": print_data.get("message") or "Tape error",
                        }
                    )
                )
            else:
                await websocket.send_text(json.dumps({**print_data, "type": "print"}))
    except WebSocketDisconnect:
        logger.debug("IBKR tape WS disconnected: %s", symbol)
    except Exception as exc:
        logger.exception("IBKR tape WS error for %s: %s", symbol, exc)
    finally:
        if viewer_opened and _tape.ws_viewer_closed(symbol):
            _tape.unsubscribe(symbol)
