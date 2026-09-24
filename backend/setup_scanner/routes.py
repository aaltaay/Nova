"""Setup scanner routes (ADR 022). Read-only: nothing here places, stages or
cancels an order.

  GET /api/setups/board               the live board (same payload the socket pushes)
  GET /api/setups/scoreboard?days=N   armed setups in the last N calendar days + summary
  GET /api/setups/rows?date=&symbol=  scoreboard rows for one day

Both scoreboard reads answer for one setup (``setup=``, the first pullback by
default; ADR 031) and its template in play -- its id and current revision, the
rules the read-out judges (ADR 029) -- unless ``template=`` names another
template id of that setup (every revision of it) or ``all`` (every template's
rows: a variation re-scores the same legs, so counts overlap). The answer names
the ``setup_type`` and the ``template`` it read.
  WS  /ws/setups                      {"type": "board", ...} every second,
                                      {"type": "alerts", "alerts": [...]} when a proposal is raised
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from constants_bot import BOT_SETUP_FIRST_PULLBACK, BOT_SETUPS_WITH_SCANNER
from scanner_wire import dumps_wire
from setup_scanner.engine import get_engine
from setup_scanner.store import session_date
from setup_scanner.summary import summarize

logger = logging.getLogger(__name__)
router = APIRouter(tags=["setups"])
SCOREBOARD_ROW_LIMIT = 500
WS_IDLE_PING_SEC = 30.0


@router.get("/api/setups/board")
def board() -> dict:
    return get_engine().board()


def _store_or_503():
    eng = get_engine()
    if eng.store is None:
        raise HTTPException(503, eng.store_error or "the scoreboard is not open yet")
    return eng.store


def _template_filter(template: str | None, setup: str) -> tuple[dict, dict | None]:
    """``(store.rows filter, the template named)`` -- the one in play when ``template`` is empty."""
    if setup not in BOT_SETUPS_WITH_SCANNER:
        raise HTTPException(404, f"{setup!r} has no scanner and no scoreboard")
    if template == "all":
        return {"setup_type": setup}, None
    from setup_templates.store import get_store

    store = get_store()
    if template:
        t = next((x for x in store.templates(setup) if x.id == template), None)
        if t is None:
            raise HTTPException(404, f"no {setup.replace('_', ' ')} template {template!r}")
        return {"setup_type": setup, "template_id": t.id}, {"id": t.id, "rev": None, "name": t.name}
    t = store.in_play(setup)
    return ({"setup_type": setup, "template_id": t.id, "template_rev": int(t.rev)},
            {"id": t.id, "rev": int(t.rev), "name": t.name})


@router.get("/api/setups/scoreboard")
def scoreboard(days: int = Query(5, ge=0, le=3650, description="calendar days back; 0 = all"),
               template: str | None = Query(None, description="a template id, 'all', or empty for the one in play"),
               setup: str = Query(BOT_SETUP_FIRST_PULLBACK, description="a setup with a scanner")) -> dict:
    store = _store_or_503()
    date_from = None if days == 0 else session_date(time.time() - (days - 1) * 86400)
    where, named = _template_filter(template, setup)
    rows = store.rows(date_from=date_from, **where)
    return {"days": days, "date_from": date_from, "setup_type": setup, "template": named,
            "summary": summarize(rows), "rows": rows[:SCOREBOARD_ROW_LIMIT], "row_count": len(rows)}


@router.get("/api/setups/rows")
def rows(date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"), symbol: str | None = None,
         template: str | None = Query(None, description="a template id, 'all', or empty for the one in play"),
         setup: str = Query(BOT_SETUP_FIRST_PULLBACK, description="a setup with a scanner, or 'all'")) -> dict:
    store = _store_or_503()
    if setup == "all":
        return {"date": date, "setup_type": "all", "template": None,
                "rows": store.rows(date_from=date, date_to=date, symbol=symbol)}
    where, named = _template_filter(template, setup)
    return {"date": date, "setup_type": setup, "template": named,
            "rows": store.rows(date_from=date, date_to=date, symbol=symbol, **where)}


@router.websocket("/ws/setups")
async def ws_setups(websocket: WebSocket) -> None:
    await websocket.accept()
    eng = get_engine()
    eng.clients.add(websocket)
    try:
        await websocket.send_text(dumps_wire({"type": "board", **eng.board()}))
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=WS_IDLE_PING_SEC)
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        logger.debug("setups socket closed")
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("setups socket failed")
    finally:
        eng.clients.discard(websocket)
