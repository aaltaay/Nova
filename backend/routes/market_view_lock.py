"""The desk's order locks in the backend log (ADR 045 amendment, operator ask 2026-10-13).

POST /api/market-view/lock -- one line per flip: the symbol, locked with its reason, or open again after
how long. At 17:39 ET the operator sent a screenshot of a Paper ticket reading "Market view behind ·
locked", and nothing on record said which stock, when or why: the desk judged the lock and told no one.
Each flip now lands in the log beside the IBKR lines that explain it ("our audit trails should be very
clear to the eye"). Log only: nothing is stored, and the backend's own order gate (``market_view.gate``)
is unchanged.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
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
