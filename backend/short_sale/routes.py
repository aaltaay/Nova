"""``GET /api/short-check/{symbol}``: the short check, read-only, before you press (ADR 048).

The ticket's SHORT CHECK box, the plan and the bot's squares show the same verdict the execution
door would give (``short_sale.check``): every rule with its numbers, its state and its fix. Asking
places nothing. It warms what the door reads -- the borrow, IBKR's what-if margin for the stock (it
may wait up to ``SHORT_WHATIF_TIMEOUT_SEC`` for IBKR here: no order is waiting), the SSR history --
so the order that follows finds them.
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException, Query

from constants_shorts import SHORT_WHATIF_TIMEOUT_SEC
from short_sale import check, door, hours
from short_sale.facts import gather, is_replay

router = APIRouter(prefix="/api/short-check", tags=["short-selling"])


def _hours(now: float) -> dict | None:
    got = hours.hours_on(now)
    if got is None:
        return None
    return {"date": got.date, "half_day": got.half_day, "open": got.open_ts, "last_short": got.last_short_ts,
            "cover": got.cover_ts, "close": got.close_ts}


@router.get("/{symbol}")
async def get_short_check(
    symbol: str,
    qty: float = Query(..., gt=0, description="shares to short"),
    price: float | None = Query(None, gt=0, description="the short's limit"),
    stop: float | None = Query(None, gt=0, description="its buy stop"),
    target: float | None = Query(None, gt=0, description="its cover target, if any"),
) -> dict:
    """Every rule's verdict for shorting ``qty`` of ``symbol`` at ``price`` with a buy stop at ``stop``."""
    from ibkr import client as _client
    from ibkr import safety as _safety
    from sim.mode import venue as desk_venue
    from short_sale import whatif

    sym = symbol.strip().upper()
    if not sym or not sym.replace(".", "").replace("/", "").isalnum():
        raise HTTPException(status_code=400, detail=f"not a symbol: {symbol!r}")
    venue = desk_venue()
    if price and _client.is_ready() and not is_replay(venue) and not whatif.fresh(sym, "SELL"):
        await whatif.ask(sym, "SELL", qty, price, timeout=SHORT_WHATIF_TIMEOUT_SEC)
    facts = await asyncio.to_thread(gather, sym, venue)
    order = check.Order(symbol=sym, qty=qty, entry=price, stop=stop, target=target)
    account = await asyncio.to_thread(door.read_account, sym, venue)
    verdicts = check.rules(order, facts, account, live_key=_safety.short_enabled() if venue == "live" else None,
                           live_proof=door.live_proof() if venue == "live" else None)
    first = check.first_refusal(verdicts)
    answer = facts.whatif
    return {
        "schema_version": 1, "symbol": sym, "venue": venue, "generated_at": time.time(), "now": facts.now,
        "replay": facts.replay, "ok": first is None,
        "first": None if first is None else {"text": first[0], "code": first[1]},
        "rules": [v.as_dict() for v in verdicts],
        "facts": {
            "bid": facts.bid, "ask": facts.ask, "last": facts.last,
            "borrow": None if facts.borrow is None else {
                "shares": facts.borrow.get("shortable_shares"), "state": facts.borrow.get("state"),
                "age_sec": facts.borrow.get("age_sec"), "stale": facts.borrow.get("stale"),
                "source": facts.borrow.get("source") or "live"},
            "whatif": None if answer is None or facts.replay else answer.as_dict(),
            "whatif_error": None if answer is not None else whatif.last_error(sym, "SELL"),
            "ssr": facts.ssr.as_dict(), "halt": facts.halt.as_dict(), "hours": _hours(facts.now),
        },
    }
