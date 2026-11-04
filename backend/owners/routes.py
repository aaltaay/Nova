"""The bots' budget and the Close on a bots' row on the wire (ADR 069).

- ``GET /api/owners/budget`` -- ``{schema_version, bots_usd, used_usd, set_at, source, error}``: the setting and
  what the bots hold against it on Paper now.
- ``PUT /api/owners/budget`` ``{bots_usd}`` -- whole dollars; a value out of its rule is a 400 with the rule.
- ``POST /api/owners/close-bots`` ``{symbol}`` -- cancels the bots' working orders in one stock on Paper, then
  sells (or covers) their shares there the way a bot's last-resort close does (``bot.flatten.place_close``), origin
  ``close_bots``; your shares and orders stay. 409 while the desk is not on Paper or the bots hold nothing there.

Shape: ``architecture/schema/recording-and-replay.md`` ("Your book and the bots' book").
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from constants_owners import (
    HOLDER_BOTS_BOOK,
    ORIGIN_CLOSE_BOTS,
    OWNERS_BUDGET_SCHEMA_VERSION,
    OWNERS_REASON_INVALID,
    OWNERS_REASON_NOTHING_TO_CLOSE,
)
from constants_practice import PRACTICE_VENUE_PAPER
from owners import budget

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/owners", tags=["owners"])


def _paper_ledger() -> Any:
    from practice.broker import for_venue

    return for_venue(PRACTICE_VENUE_PAPER).ledger


def _budget_view() -> dict[str, Any]:
    return {"schema_version": OWNERS_BUDGET_SCHEMA_VERSION, **budget.current(),
            "used_usd": round(budget.used_usd(_paper_ledger()), 2)}


@router.get("/budget")
def get_budget() -> dict[str, Any]:
    return _budget_view()


@router.put("/budget")
async def put_budget(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or "bots_usd" not in body:
        raise HTTPException(status_code=400, detail={"code": OWNERS_REASON_INVALID, "error": "Send {bots_usd}"})
    try:
        await asyncio.to_thread(budget.update, body["bots_usd"])
    except budget.Invalid as exc:
        raise HTTPException(status_code=400, detail={"code": OWNERS_REASON_INVALID, "error": str(exc)}) from exc
    return _budget_view()


@router.post("/close-bots")
async def close_bots(request: Request) -> dict[str, Any]:
    from sim.account_hooks import held_by_if_practice
    from sim.mode import venue

    try:
        body = await request.json()
    except ValueError:
        body = None
    symbol = str((body or {}).get("symbol") or "").strip().upper() if isinstance(body, dict) else ""
    if not symbol:
        raise HTTPException(status_code=400, detail={"code": OWNERS_REASON_NOTHING_TO_CLOSE, "error": "Send {symbol}"})
    if venue() != PRACTICE_VENUE_PAPER:
        raise HTTPException(status_code=409, detail={"code": OWNERS_REASON_NOTHING_TO_CLOSE,
                                                     "error": "The bots' shares are closed on Paper: switch the desk to Paper"})
    held = held_by_if_practice(symbol, HOLDER_BOTS_BOOK) or 0.0
    if abs(held) < 1e-9:
        raise HTTPException(status_code=409, detail={"code": OWNERS_REASON_NOTHING_TO_CLOSE,
                                                     "error": f"The bots hold no {symbol}"})
    from bot.flatten import cancel_working, place_close

    side = "SELL" if held > 0 else "BUY"
    # Their stops and entries leave first (never cancel after a place, ``bot.flatten``): a stop left working over
    # shares that are gone would sit in Working until it fired and Paper refused it.
    cancels = await cancel_working(symbol=symbol, owner=HOLDER_BOTS_BOOK)
    # Paper's alone: the door refuses it if the desk moves before it is sent (``execution.venue_door``).
    out = await place_close(symbol, abs(held), side, origin=ORIGIN_CLOSE_BOTS, expected_venue=PRACTICE_VENUE_PAPER)
    logger.info("OWNERS: the operator closed the bots' %s %s (%s, %d cancelled)", abs(held), symbol,
                "ok" if out.get("ok") else out, len(cancels))
    return {"symbol": symbol, "qty": abs(held), "side": side, **out, "cancels": cancels}
