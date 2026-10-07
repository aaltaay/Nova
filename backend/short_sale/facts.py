"""What the short check knows about a stock right now, gathered outside the execution lock (ADR 048).

The execution door gathers a short entry's facts before it takes its lock (``execution.service``):
the borrow, IBKR's what-if margin for the stock, SSR, the halt state, the venue's quote and clock.
Each read is memory or a small local file, never a wait on IBKR -- what IBKR has not answered is
asked for in the background and stands as unknown, or as the published rules, until it does. The
read-only check (``GET /api/short-check/{symbol}``) gathers the same facts.

**The venue decides where they come from.** Live, Paper and Sim at the live edge read the live
feed: the shortability cache, ``short_sale.ssr.live``, ``short_sale.halts.live``. A past-day Sim
replay (Sim off the live edge) reads what was recorded at its playhead and never after it: borrow
from ``short_sale.borrow_log``, the day's halt log, the replay's own prints for SSR -- and the
published margin rules, which IBKR's what-if cannot speak for.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from constants import IBKR_SHORTABILITY_TTL_SEC
from short_sale import halts, ssr, whatif
from short_sale.hours import ET, clock, venue_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Facts:
    venue: str
    symbol: str
    now: float                      # the venue's clock
    replay: bool                    # a past-day Sim replay: Sim off the live edge
    borrow: dict[str, Any] | None   # a shortability snapshot, live or recorded
    borrow_why: str | None          # why a replay has none
    whatif: whatif.Answer | None    # IBKR's answer for this stock's short, kept within the day
    ssr: ssr.SsrRead
    halt: halts.HaltRead
    bid: float | None
    ask: float | None
    last: float | None


def is_replay(venue: str) -> bool:
    if venue != "sim":
        return False
    from sim import session_clock

    return not session_clock.live_edge()


def _recorded_borrow(symbol: str, at: float) -> tuple[dict[str, Any] | None, str | None]:
    """The read recorded at or before the playhead, shaped as the live cache's, or why there is none."""
    from ibkr.shortability import enrich_ibkr_listing
    from short_sale import borrow_log

    try:
        row = borrow_log.at(symbol, at)
    except Exception as exc:  # an unreadable or foreign store is no recorded borrow, and says why
        return None, f"Nova cannot read its recorded borrow ({exc})."
    day = datetime.fromtimestamp(at, ET).date().isoformat()
    if row is None:
        return None, (f"Nova has no borrow recorded for {symbol} at or before {clock(at)} ET on {day}: a "
                      "past-day replay shorts only where IBKR's borrow was recorded then.")
    age = at - float(row["ts"])
    if age > float(IBKR_SHORTABILITY_TTL_SEC):
        return None, (f"The last borrow Nova recorded for {symbol} before {clock(at)} ET on {day} is from "
                      f"{clock(float(row['ts']))}, {age / 60:.0f} min earlier: a past-day replay shorts only where "
                      "IBKR's borrow was recorded then.")
    snap = enrich_ibkr_listing({"connected": True, "qualified": True, "shortable_shares": row["shares"]},
                               fetched_at=time.time() - age)
    snap["recorded_at"] = float(row["ts"])
    snap["source"] = "recorded"
    return snap, None


def _quote(venue: str, symbol: str) -> tuple[float | None, float | None, float | None]:
    try:
        from practice.broker import for_venue

        if venue in ("paper", "sim"):
            ref = for_venue(venue).reference.reference(symbol)
            return ref.bid, ref.ask, ref.last
        from ibkr import ticks as _ticks

        ticker = _ticks.get_ticker(symbol)
        q = _ticks.last_quotes([symbol]).get(symbol) or {}
        bid = getattr(ticker, "bid", None)
        ask = getattr(ticker, "ask", None)
        last = None if q.get("quote_quality") == "close_fallback" else q.get("price")
        return _positive(bid), _positive(ask), _positive(last)
    except Exception:  # a quote Nova cannot read is unknown: SSR then refuses rather than guesses
        logger.debug("short facts: quote unread for %s on %s", symbol, venue, exc_info=True)
        return None, None, None


def _positive(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if x == x and x > 0 else None


def gather(symbol: str, venue: str, *, borrow: dict[str, Any] | None = None, now: float | None = None) -> Facts:
    """The facts for a short of ``symbol`` on ``venue`` at the venue's clock (``now`` for tests).

    ``borrow`` is the live cache's read when the caller took it already (the door, before its lock).
    """
    from ibkr import shortability

    sym = (symbol or "").strip().upper()
    at = float(now) if now is not None else venue_now(venue)
    replay = is_replay(venue)
    bid, ask, last = _quote(venue, sym)
    if replay:
        from practice.broker import for_venue

        day = datetime.fromtimestamp(at, ET).date().isoformat()
        prints = for_venue("sim").reference.prints_between
        snap, why = _recorded_borrow(sym, at)
        return Facts(venue=venue, symbol=sym, now=at, replay=True, borrow=snap, borrow_why=why, whatif=None,
                     ssr=ssr.replay(sym, at, day, prints), halt=halts.replay(sym, at, day, prices=prints),
                     bid=bid, ask=ask, last=last)
    snap = borrow if borrow is not None else shortability.for_order(sym)
    ssr.request_history(sym, at)
    return Facts(venue=venue, symbol=sym, now=at, replay=False, borrow=snap, borrow_why=None,
                 whatif=whatif.answer_for(sym, "SELL", now=time.time()), ssr=ssr.live(sym, at),
                 halt=halts.live(sym, at), bid=bid, ask=ask, last=last)
