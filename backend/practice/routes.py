"""``GET /api/practice/account``, ``GET /api/practice/history`` and ``POST /api/practice/reset`` (ADR 020)."""
from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from constants_practice import PRACTICE_HISTORY_RANGE_DEFAULT, PRACTICE_VENUE_PAPER, PRACTICE_VENUE_SIM

router = APIRouter(prefix="/api/practice", tags=["practice"])

_VENUES = (PRACTICE_VENUE_PAPER, PRACTICE_VENUE_SIM)


class PracticeResetRequest(BaseModel):
    venue: str = Field(description="paper | sim")
    starting_cash: float | None = Field(
        default=None, description="New starting cash; the constant default when omitted",
    )


def _broker(venue: str | None):
    key = (venue or "").strip().lower()
    if key not in _VENUES:
        raise HTTPException(status_code=400, detail=f"venue must be one of {', '.join(_VENUES)}, not {venue!r}")
    from practice.broker import for_venue

    return for_venue(key)


@router.get("/account")
def get_practice_account(venue: str = Query(..., description="paper | sim")) -> dict:
    """The venue's practice account: cash, buying power, P&L, positions, working orders."""
    return _broker(venue).snapshot()


@router.get("/history")
def get_practice_history(
    venue: str = Query(..., description="paper | sim"),
    range_: str = Query(PRACTICE_HISTORY_RANGE_DEFAULT, alias="range", description="1D | 5D | 1M | 3M | YTD | ALL"),
) -> dict:
    """The venue's ledger as history: equity after each event, fills, by-source split, daily rows, archives."""
    from practice import history

    try:
        range_key = history.normalize_range(range_)
    except history.RangeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return history.for_broker(_broker(venue), range_key)


@router.post("/reset")
def post_practice_reset(body: PracticeResetRequest) -> dict:
    """A fresh account. Paper archives its old ledger beside the new one; Sim starts over."""
    broker = _broker(body.venue)
    cash = body.starting_cash
    if cash is not None and not (math.isfinite(cash) and cash > 0):
        raise HTTPException(status_code=422, detail="starting_cash must be a positive number")
    return broker.reset(cash)
