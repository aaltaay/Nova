"""
HOD Momo REST + WebSocket routes.

Extracted from ``main.py`` — thin handlers that delegate entirely to
``hod_momo.py`` and ``strategy/setups_stream.py``.

Endpoints:
  GET  /api/hod-momo/alerts
  GET  /api/hod-momo/history/dates
  GET  /api/hod-momo/history/{date}
  GET  /api/hod-momo/config
  POST /api/hod-momo/config
  GET  /api/hod-momo/blocklist
  POST /api/hod-momo/blocklist
  DELETE /api/hod-momo/blocklist/{symbol}
  GET  /api/hod-momo/debug/counters
  GET  /api/hod-momo/debug/symbol/{sym}
  GET  /api/hod-momo/debug/recent
  GET  /api/hod-momo/debug/snaps
  WS   /ws/hod-momo
  WS   /ws/strategy
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger(__name__)

import hod_momo as _hod_momo
import strategy.setups_stream as _setups_stream
from cache import list_history_dates as _list_history_dates
from hod_momo_session import current_date_et
from runtime_state import get_runtime_state
from constants import HOD_MOMO_UNIVERSE_MODE, HOD_MOMO_UNIVERSE_MODE_FOCUS

router = APIRouter(tags=["hod-momo"])
ws_router = APIRouter(tags=["hod-momo-ws"])


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.get("/api/hod-momo/alerts")
def hod_momo_get_alerts(limit: int | None = None):
    """Today's HOD Momo alert feed (newest first).

    Optional ``limit`` caps the payload for observers (still newest-first).
    """
    alerts = _hod_momo.get_today_alerts()
    if limit is not None and limit > 0:
        alerts = alerts[: int(limit)]
    return {"date": current_date_et(), "alerts": alerts}


@router.delete("/api/hod-momo/alerts")
async def hod_momo_clear_alerts():
    """Explicitly clear today's alerts (in-memory + today's on-disk snapshot)."""
    result = _hod_momo.clear_today_alerts()
    payload = json.dumps(_hod_momo.get_ws_initial_payload())
    dead = []
    for ws in list(_hod_momo.get_ws_clients()):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _hod_momo.remove_ws_client(ws)
    return result


@router.get("/api/hod-momo/history/dates")
def hod_momo_history_dates():
    """Past dates for which HOD Momo alert snapshots exist."""
    return {"dates": _list_history_dates("hod-momo")}


@router.get("/api/hod-momo/history/{date}")
def hod_momo_history_snapshot(date: str):
    """HOD Momo alerts for a historical date (YYYY-MM-DD)."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return {}
    return _hod_momo.get_history_alerts(date)


@router.get("/api/hod-momo/config")
def hod_momo_get_config():
    """Return all strategy configs + master gate config."""
    return _hod_momo.get_configs()


class HodMomoConfigPatch(BaseModel):
    scope: str
    strategy_id: int | None = None
    patch: dict | None = None


@router.post("/api/hod-momo/config")
def hod_momo_update_config(body: HodMomoConfigPatch):
    """Update a strategy config, the master gate, or reset everything."""
    if body.scope == "reset_all":
        return _hod_momo.reset_all()
    if body.scope == "reset_one":
        if body.strategy_id is None:
            return {"error": "strategy_id required"}
        result = _hod_momo.reset_config(body.strategy_id)
        return result if result is not None else {"error": "unknown strategy_id"}
    if body.scope == "master":
        return _hod_momo.update_master(body.patch or {})
    if body.scope == "strategy":
        if body.strategy_id is None:
            return {"error": "strategy_id required"}
        result = _hod_momo.update_config(body.strategy_id, body.patch or {})
        return result if result is not None else {"error": "unknown strategy_id"}
    return {"error": "unknown scope"}


@router.get("/api/hod-momo/blocklist")
def hod_momo_get_blocklist():
    return {"symbols": _hod_momo.get_blocklist()}


class HodMomoBlocklistUpdate(BaseModel):
    symbol: str


@router.post("/api/hod-momo/blocklist")
def hod_momo_add_block(body: HodMomoBlocklistUpdate):
    return {"symbols": _hod_momo.add_block(body.symbol)}


@router.delete("/api/hod-momo/blocklist/{symbol}")
def hod_momo_remove_block(symbol: str):
    return {"symbols": _hod_momo.remove_block(symbol)}


# ── Debug endpoints ───────────────────────────────────────────────────────────

@router.get("/api/hod-momo/debug/counters")
def hod_momo_debug_counters():
    """Gate counters, universe size, snaps — polled by the Debug panel."""
    out = _hod_momo.get_debug_counters()
    out["watch_universe_size"] = len(get_runtime_state().hod_momo_universe)
    out["watch_universe_mode"] = (
        (HOD_MOMO_UNIVERSE_MODE or HOD_MOMO_UNIVERSE_MODE_FOCUS).strip().lower()
    )
    return out


@router.get("/api/hod-momo/debug/symbol/{sym}")
def hod_momo_debug_symbol(sym: str):
    """Current snapshot + last 20 decisions for a specific symbol."""
    return _hod_momo.get_debug_symbol(sym.upper())


@router.get("/api/hod-momo/debug/recent")
def hod_momo_debug_recent(limit: int = 100):
    """Last N decisions across all symbols."""
    return {"decisions": _hod_momo.get_debug_recent(min(limit, 500))}


@router.get("/api/hod-momo/debug/snaps")
def hod_momo_debug_snaps(limit: int = 50):
    """Top-N most-recently enriched snapshots (sanity-check for the enrichment loop)."""
    return {"snaps": _hod_momo.get_debug_snaps(min(limit, 200))}


@router.get("/api/hod-momo/debug/integrity")
def hod_momo_debug_integrity():
    """Fail-loud HOD data-flow integrity (ticks, surge seed, active-set ages)."""
    from integrity_live import build_hod_integrity_report
    return build_hod_integrity_report()


# ── WebSocket endpoints ───────────────────────────────────────────────────────

@ws_router.websocket("/ws/hod-momo")
async def ws_hod_momo(websocket: WebSocket):
    """WebSocket: sends today's alerts on connect, then pushes live alerts."""
    await websocket.accept()
    _hod_momo.add_ws_client(websocket)
    try:
        initial = json.dumps(_hod_momo.get_ws_initial_payload())
        await websocket.send_text(initial)
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        logger.debug("HOD Momo WS client disconnected")
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("HOD Momo WS loop failed")
    finally:
        _hod_momo.remove_ws_client(websocket)


@ws_router.websocket("/ws/strategy")
async def ws_strategy(websocket: WebSocket):
    """WebSocket: Gap and Go / Bull Flag / ABCD signals. Signal only — never places orders."""
    await websocket.accept()
    _setups_stream.add_ws_client(websocket)
    try:
        initial = json.dumps({
            "type": "initial",
            "note": "Signal only. This stream never places, modifies, or cancels orders.",
            "signals": _setups_stream.get_signal_history(),
        })
        await websocket.send_text(initial)
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        logger.debug("Strategy WS client disconnected")
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Strategy WS loop failed")
    finally:
        _setups_stream.remove_ws_client(websocket)
