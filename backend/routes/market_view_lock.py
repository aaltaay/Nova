"""The desk's order locks in the backend log (ADR 045 amendment, operator ask 2026-10-13).

POST /api/market-view/lock -- one line per flip: the symbol, locked with its reason, or open again after
how long. At 17:39 ET the operator sent a screenshot of a Paper ticket reading "Market view behind ·
locked", and nothing on record said which stock, when or why: the desk judged the lock and told no one.
Each flip now lands in the log beside the IBKR lines that explain it ("our audit trails should be very
clear to the eye"). Log only: nothing is stored, and the backend's own order gate (``market_view.gate``)
is unchanged.

GET /api/market-view/gate?symbol= -- the backend's own answer for a symbol now (ADR 045 amendment
2026-10-14, "one funnel"): ``{schema_version, symbol, locked, code, text, checked_at}``, from the same
``market_view.gate.desk_lock`` the order door refuses with.
"""
from __future__ import annotations

import logging

import time

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["market-view"])
logger = logging.getLogger("nova.order_lock")

_REASON_MAX = 600


class LockFlip(BaseModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    symbol: str = Field(min_length=1, max_length=16)
    locked: bool
    reason: str | None = Field(default=None, max_length=_REASON_MAX)
    locked_for_ms: int | None = Field(default=None, ge=0)


@router.post("/api/market-view/lock")
async def post_lock_flip(body: LockFlip) -> dict:
    """Write one line for one flip of a desk window's order lock."""
    symbol = body.symbol.strip().upper()
    if body.locked:
        logger.warning("order lock ON  %s -- %s", symbol, body.reason or "no reason given")
    else:
        held = f"{body.locked_for_ms / 1000:.1f} s" if body.locked_for_ms is not None else "an unknown time"
        logger.info("order lock OFF %s -- open again after %s", symbol, held)
    return {"ok": True}


@router.get("/api/market-view/gate")
def get_gate(symbol: str = Query(..., min_length=1, max_length=16)) -> dict:
    """Whether new orders on *symbol* are locked right now, and why, in the door's own words."""
    from constants_market_view import MARKET_VIEW_SCHEMA_VERSION
    from market_view.gate import desk_lock

    sym = symbol.strip().upper()
    now = time.time()
    lock = desk_lock(sym, now=now)
    return {
        "schema_version": MARKET_VIEW_SCHEMA_VERSION,
        "symbol": sym,
        "locked": lock is not None,
        "code": lock["code"] if lock else None,
        "text": lock["text"] if lock else None,
        "checked_at": now,
    }
