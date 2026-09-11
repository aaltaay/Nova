"""
IBKR trading routes — thin handlers that delegate to ibkr/*.py modules.

Endpoints:
  GET  /api/ibkr/status           -- connection state + mode (paper/live/disconnected)
  POST /api/ibkr/reconnect        -- reload .env + reconnect to configured port
  POST /api/ibkr/gateway-mode     -- user-initiated Paper<->Live port switch (no spend unlock)
  GET  /api/ibkr/gateway-trail    -- Paper/Live click + attach/refuse trail
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

import asyncio
import json
import logging

from fastapi import APIRouter, Body, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from execution import closed_blotter as _closed_blotter
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
    from ibkr import second_factor as _second_factor
    from ibkr import session_errors as _session_errors
    from ibkr import session_state as _session_state

    # Product "connected" = usable session (get_ib() non-None). Transport is
    # separate so port hints / Authenticating ops stay honest.
    from ibkr import ib_scheduler as _ib_scheduler
    from ibkr import session_reconnect as _reconnect
    from ibkr import session_usable as _session_usable
    from ibkr import ticks as _ticks

    usable = _client.is_ready()
    transport = _client.is_connected()
    sf_state = _second_factor.current_state()
    return {
        "enabled": _client.is_enabled(),
        "connected": usable,
        "transport_connected": transport,
        "session_reason": _client.session_reason(),
        "session_state": _session_state.state(),
        "session_generation": _session_state.generation(),
        "mode": _client.account_mode(),
        "broker_account_kind": _client.broker_account_kind(),
        "market_data_type": _client.get_market_data_type(),
        "market_data_delayed": bool(_session_errors.is_delayed_data()),
        **snap,
        **_heal.heal_status(),
        **_ports.status_port_fields(connected=transport),
        "second_factor_pending": sf_state.pending,
        "second_factor_age_sec": sf_state.age_sec,
        "second_factor_stale": sf_state.stale,
        "gateway_trail": _gateway_trail_tail(),
        # See PROBLEM_LOG 2026-08-31 -- one query instead of an hour of log
        # archaeology the next time the session freezes with the port open.
        "earn_in_flight": _session_usable.earn_in_flight(),
        "ib_cold_inflight": _ib_scheduler.inflight_label() or None,
        "dialer_heartbeat_age_sec": _reconnect.dialer_heartbeat_age_sec(),
        **_ticks.ticker_budget_status(),
    }


def _gateway_trail_tail() -> list[dict]:
    from ibkr.gateway_trail import recent

    return recent(limit=8)


@router.post("/reconnect")
async def ibkr_reconnect() -> dict:
    """Reload .env (override) and reconnect to the configured Gateway port."""
    return await _client.force_reconnect()


class GatewayModeRequest(BaseModel):
    mode: str  # "paper" | "live"


class LaunchGatewayRequest(BaseModel):
    mode: str | None = None  # optional paper | live -- pick a door
    force_fresh_login: bool = False  # explicit re-auth: clear jts.ini Restart=OK


@router.post("/gateway-mode")
async def ibkr_gateway_mode(body: GatewayModeRequest) -> dict:
    """User-initiated Paper↔Live switch — persists + reconnects; never unlocks spend."""
    mode = (body.mode or "").strip().lower()
    if mode not in ("paper", "live"):
        raise HTTPException(status_code=400, detail=f"invalid mode {body.mode!r} (must be paper or live)")
    return await _client.request_gateway_mode(mode)


@router.get("/gateway-trail")
async def ibkr_gateway_trail(limit: int = 40) -> dict:
    """Paper/Live door trail -- who requested what, and whether the account class matched."""
    from ibkr.gateway_trail import recent

    cap = max(1, min(int(limit), 200))
    return {"ok": True, "events": recent(limit=cap)}


@router.post("/launch-gateway")
async def ibkr_launch_gateway(body: LaunchGatewayRequest | None = Body(default=None)) -> dict:  # noqa: B008 -- FastAPI dependency marker
    """Start IB Gateway (or focus it). Optional mode restarts IBC as paper or live.

    ``force_fresh_login`` is the "Start fresh login" CTA for a stale Second
    Factor prompt -- it clears jts.ini Restart=OK so IBC opens a genuinely
    new live login instead of reusing the week-long token.

    ``already_listening`` (port is up, no restart needed) used to be the
    end of the story even when Nova's own session was not READY on that
    port -- the operator's click focused a healthy Gateway window and did
    nothing for a frozen Nova session (PROBLEM_LOG 2026-08-31: 7 hours
    stuck with the port open the whole time). When that happens, rebuild
    the Nova-side session instead of leaving the button a no-op.
    """
    from ibkr.launch_gateway import launch_or_focus_gateway

    result = launch_or_focus_gateway(
        mode=body.mode if body else None,
        force_restart=bool(body.force_fresh_login) if body else False,
        force_fresh_login=bool(body.force_fresh_login) if body else False,
    )
    if result.get("action") == "already_listening" and not _client.is_ready():
        rebuild = await _client.force_reconnect()
        note = "Nova's session was not READY -- rebuilt the connection instead of only focusing the window."
        result = {
            **result,
            "action": "rebuild_session",
            "connected": rebuild.get("connected"),
            "session_state": rebuild.get("session_state"),
            "message": f"{result.get('message', '')} {note}".strip(),
        }
    return result


def _client_safety_status() -> dict:
    from ibkr import safety as _safety
    return _safety.status_snapshot(_client.broker_account_kind())


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
        rows = await _orders.closed_orders_async(limit=limit)
        return _closed_blotter.overlay_closed_orders(rows, limit=limit)
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
    queue: asyncio.Queue | None = None
    try:
        _depth.ws_viewer_opened(symbol)
        viewer_opened = True

        # Remount race: a previous viewer's cleanup may have dropped the line
        # between our initial subscribe check and viewer_opened. Re-subscribe
        # before streaming so the line actually exists to hold a viewer queue.
        if not _depth.is_subscribed(symbol):
            result = await _depth.subscribe_async(symbol)
            if not result["ok"]:
                await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
                return
            try:
                _l2_continuous.start(symbol)
            except Exception:
                logger.exception("l2.continuous: failed to restart for WS %s", symbol)

        # Own queue per viewer -- a shared per-symbol queue makes concurrent
        # viewers (StrictMode double-mount, or a second Trader tab on the
        # same symbol) competing consumers instead of both seeing every book
        # update (same defect class as tape_stream.py -- PROBLEM_LOG 2026-08-25).
        queue = _depth.open_viewer_queue(symbol)
        await websocket.send_text(json.dumps({"type": "subscribed", "symbol": symbol}))

        # A symbol already subscribed by another viewer (or a fresh page
        # reload re-attaching to a still-open depth line) needs today's
        # snapshot right away — see should_send_current_book().
        current = _depth.current_book(symbol)
        if _depth.should_send_current_book(current):
            await websocket.send_text(json.dumps({"type": "book", "symbol": symbol, "data": current}))

        async for item in _depth.stream(queue):
            if item is None:
                # Heartbeat timeout
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue
            if item.get("type") == "error":
                # Line torn down out from under this viewer -- tell the
                # client, then close so its onclose backoff reconnects
                # (PROBLEM_LOG 2026-08-25). Live 4th-symbol refuses never
                # evict, so this path is unsubscribe / idle reclaim.
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "symbol": symbol,
                            "message": item.get("message") or "Depth error",
                        }
                    )
                )
                if item.get("evicted"):
                    await websocket.close()
                    break
            else:
                await websocket.send_text(json.dumps({"type": "book", "symbol": symbol, "data": item}))
    except WebSocketDisconnect:
        logger.debug("IBKR depth WS disconnected: %s", symbol)
    except Exception as exc:
        from ws_close_errors import is_websocket_send_after_close

        if is_websocket_send_after_close(exc):
            logger.debug("IBKR depth WS send-after-close: %s", symbol)
        else:
            logger.exception("IBKR depth WS error for %s: %s", symbol, exc)
    finally:
        if queue is not None:
            _depth.close_viewer_queue(symbol, queue)
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

    if not _tape.is_subscribed(symbol):
        result = await _tape.subscribe_async(symbol)
        if not result["ok"]:
            await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
            await websocket.close()
            return

    viewer_opened = False
    queue: asyncio.Queue | None = None
    try:
        _tape.ws_viewer_opened(symbol)
        viewer_opened = True

        # Remount race: previous viewer cleanup may have dropped the line.
        if not _tape.is_subscribed(symbol):
            result = await _tape.subscribe_async(symbol)
            if not result["ok"]:
                await websocket.send_text(json.dumps({"type": "error", "message": result["error"]}))
                return

        # Own queue per viewer -- a shared per-symbol queue makes concurrent
        # viewers (StrictMode double-mount, or a second Trader tab on the
        # same symbol) competing consumers instead of both seeing every
        # print (PROBLEM_LOG 2026-08-25: a live soak proved this starved
        # the surviving viewer for 1,902 archived prints).
        queue = _tape.open_viewer_queue(symbol)
        await websocket.send_text(json.dumps({"type": "subscribed", "symbol": symbol}))

        async for print_data in _tape.stream(queue):
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
                if print_data.get("released"):
                    # Line was torn down (idle-linger release) -- close so
                    # the client's onclose backoff reconnects it instead of
                    # sitting on a dead line behind a stale "LIVE" badge.
                    await websocket.close()
                    break
            else:
                await websocket.send_text(json.dumps({**print_data, "type": "print"}))
    except WebSocketDisconnect:
        logger.debug("IBKR tape WS disconnected: %s", symbol)
    except Exception as exc:
        from ws_close_errors import is_websocket_send_after_close

        if is_websocket_send_after_close(exc):
            logger.debug("IBKR tape WS send-after-close: %s", symbol)
        else:
            logger.exception("IBKR tape WS error for %s: %s", symbol, exc)
    finally:
        if queue is not None:
            _tape.close_viewer_queue(symbol, queue)
        if viewer_opened and _tape.ws_viewer_closed(symbol):
            _tape.unsubscribe(symbol)
