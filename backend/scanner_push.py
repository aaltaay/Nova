"""Push scanner table price patches / roster events to WebSocket clients."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import scanner_tab_registry as _tabs
from runtime_state import get_runtime_state
from runtime_state.state import TableState
from scanner_surface import surface_rows
from scanner_wire import dumps_wire
from metrics.op_metrics import timed_async

logger = logging.getLogger(__name__)

router = APIRouter()
_clients: set[WebSocket] = set()


def _table_meta(ts: TableState) -> dict[str, Any]:
    return {
        "state": ts.state,
        "session_key": ts.session_key,
        "revision": ts.revision,
        "roster_ts": ts.roster_ts,
        "quote_ts": ts.quote_ts,
        "frozen_at": ts.frozen_at,
        "source": ts.source,
    }


@timed_async("ws.scanner.broadcast")
async def broadcast(payload: dict[str, Any]) -> None:
    """Send a scanner WS event to every /ws/scanner client.

    Non-finite floats go out as null (QA C32): a bare NaN token makes the
    browser's JSON.parse drop the whole frame.
    """
    if not _clients:
        return
    text = dumps_wire(payload)
    dead: list[WebSocket] = []
    for ws in list(_clients):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)
        _tabs.clear(ws)


async def broadcast_roster_replace(table: str, rows: list[dict], ts: TableState) -> None:
    """Structural roster replace for one table (ADR 008).

    Rows go through the same surface as REST (``scanner_surface``): blocklist
    out, exchange + reference columns in, Large Cap scored -- so a roster
    replace cannot bring back a blocklisted ticker or blank the Large Cap
    Score the REST surface is already showing (QA C49).
    """
    await broadcast({
        "type": "roster_replace",
        "table": table,
        "rows": surface_rows(rows, table),
        "meta": _table_meta(ts),
        "ts": ts.roster_ts or time_now(),
    })


async def broadcast_table_state(table: str, ts: TableState) -> None:
    await broadcast({
        "type": "table_state",
        "table": table,
        "meta": _table_meta(ts),
        "ts": time_now(),
    })


def time_now() -> float:
    import time
    return time.time()


def _snapshot_payload() -> dict[str, Any]:
    """Current table rows + metadata for WS connect/reconnect bootstrap."""
    from ibkr import scanner_session as _ss

    state = get_runtime_state()
    tables = {
        _ss.TABLE_GAPPERS: (state.gapper_cache, state.gapper_table),
        _ss.TABLE_GAINERS: (state.gainer_cache, state.gainer_table),
        _ss.TABLE_LOSERS: (state.loser_cache, state.loser_table),
        _ss.TABLE_AFTERHOURS: (state.afterhours_cache, state.afterhours_table),
        _ss.TABLE_LARGE_CAP: (state.large_cap_cache, state.large_cap_table),
    }
    out: dict[str, Any] = {}
    for name, (rows, meta) in tables.items():
        out[name] = {
            "rows": surface_rows(rows, name),
            "meta": _table_meta(meta),
        }
    return out


@router.websocket("/ws/scanner")
async def ws_scanner(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    try:
        await websocket.send_text(dumps_wire({
            "type": "subscribed",
            "tab": "none",
            "tables": _snapshot_payload(),
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
                # `tabs` is the full set of scanner tables this desk displays
                # (main tab + scanner dock). `tab` remains for older clients.
                raw = msg.get("tabs")
                if not isinstance(raw, list):
                    raw = [msg.get("tab") or "none"]
                tabs = _tabs.set_tabs(websocket, [str(t) for t in raw])
                await websocket.send_text(dumps_wire({
                    "type": "subscription_state",
                    "tab": tabs[0] if tabs else "none",
                    "tabs": tabs,
                    "tables": _tabs.get_active_tables(),
                    "dominant_tab": _tabs.get_dominant_tab(),
                }))
    except WebSocketDisconnect:
        logger.debug("scanner WS client disconnected")
    except Exception as exc:
        logger.debug("scanner WS closed: %s", exc)
    finally:
        _clients.discard(websocket)
        _tabs.clear(websocket)
