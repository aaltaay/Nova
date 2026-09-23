"""Setup scanner routes (ADR 022). Read-only: nothing here places, stages or
cancels an order.

  GET /api/setups/board               the live board (same payload the socket pushes)
  GET /api/setups/scoreboard?days=N   armed setups in the last N calendar days + summary
  GET /api/setups/rows?date=&symbol=  scoreboard rows for one day
  WS  /ws/setups                      {"type": "board", ...} every second,
                                      {"type": "alerts", "alerts": [...]} when a proposal is raised
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

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


@router.get("/api/setups/scoreboard")
def scoreboard(days: int = Query(5, ge=0, le=3650, description="calendar days back; 0 = all")) -> dict:
    store = _store_or_503()
    date_from = None if days == 0 else session_date(time.time() - (days - 1) * 86400)
    rows = store.rows(date_from=date_from)
    return {"days": days, "date_from": date_from, "summary": summarize(rows),
            "rows": rows[:SCOREBOARD_ROW_LIMIT], "row_count": len(rows)}


@router.get("/api/setups/rows")
def rows(date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"), symbol: str | None = None) -> dict:
    store = _store_or_503()
    return {"date": date, "rows": store.rows(date_from=date, date_to=date, symbol=symbol)}


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
