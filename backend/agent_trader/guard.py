"""Nova's guard on Claude's open trade, and the pop exit's stop to entry (ADR 068 decision 13).

While Claude holds shares, every watcher pass (``AGENT_TICK_SEC``, 0.5 s) judges three conditions on the live book
and the last prints and sells Claude's shares at market the moment one holds -- no arming, no Claude in the loop:

1. **sellers lead**: in the last ``AGENT_GUARD_SELLERS_SECONDS`` at least ``AGENT_GUARD_SELLERS_MIN_SHARES`` traded at
   or under the bid and at least ``AGENT_GUARD_SELLERS_RATIO`` times what lifted the ask (``reflexes.flow``);
2. **the bids left**: the top ``AGENT_GUARD_BID_LEVELS`` bid prices, added up across market makers, hold under
   ``AGENT_GUARD_BID_STACK_FRACTION`` of what they held when the position was first seen;
3. **the bid fell under entry**: the best bid is ``AGENT_GUARD_BID_UNDER_ENTRY_PCT`` or more under Claude's entry.

A condition with nothing to read (no book, a Level 1 stand-in, no prints) is not judged; the bracket's stop still
rests. Claude's entry is the average of its buys since its position in the stock was last flat.

Owner: the marks (in memory, by symbol: the entry, the bid stack then, when it was first seen, and whether the pop
exit's stop has moved). A restart marks the stack again from the book it finds. Pure over what it is handed; the
watcher does the selling (``watcher._guard``).
"""
from __future__ import annotations

from typing import Any

from agent_trader import reflexes
from agent_trader.constants_agent_trader import (
    AGENT_GUARD_BID_LEVELS,
    AGENT_GUARD_BID_STACK_FRACTION,
    AGENT_GUARD_BID_UNDER_ENTRY_PCT,
    AGENT_GUARD_RETRY_SEC,
    AGENT_GUARD_SELLERS_MIN_SHARES,
    AGENT_GUARD_SELLERS_RATIO,
    AGENT_GUARD_SELLERS_SECONDS,
)

_marks: dict[str, dict[str, Any]] = {}
_fired_at: dict[str, float] = {}


def reset_for_tests() -> None:
    _marks.clear()
    _fired_at.clear()


def entry_of(fills: list[dict[str, Any]], symbol: str) -> tuple[float | None, float | None]:
    """``(average entry, when the position opened)`` from Claude's fills (time order) since it was last flat."""
    sym = symbol.upper()
    qty = cost = 0.0
    opened = None
    for row in fills:
        if str(row.get("symbol") or "").upper() != sym:
            continue
        size, px = float(row.get("filled_qty") or 0.0), float(row.get("avg_fill_price") or 0.0)
        if str(row.get("side") or "").upper() == "BUY":
            if qty <= 1e-9:
                qty, cost, opened = 0.0, 0.0, float(row.get("fill_ts") or 0.0)
            qty += size
            cost += size * px
        else:
            qty = max(0.0, qty - size)
            cost = cost * (qty / (qty + size)) if qty + size > 0 else 0.0
    return (cost / qty if qty > 1e-9 else None), opened


def bid_stack(book: dict[str, Any] | None) -> float | None:
    """Shares on the top ``AGENT_GUARD_BID_LEVELS`` bid prices; None without a real book (a Level 1 stand-in)."""
    if not book or book.get("l1_fallback"):
        return None
    levels = reflexes.levels(book, "bids")
    if not levels:
        return None
    return sum(size for _, size in sorted(levels.items(), reverse=True)[:AGENT_GUARD_BID_LEVELS])


def best_bid(book: dict[str, Any] | None, l1_bid: float | None = None) -> float | None:
    levels = reflexes.levels(book, "bids")
    if levels:
        return max(levels)
    return l1_bid if l1_bid is not None and l1_bid > 0 else None


def mark(symbol: str, fills: list[dict[str, Any]], book: dict[str, Any] | None, now: float) -> dict[str, Any] | None:
    """The position's mark, made when the guard first sees it (the stack taken from the first real book)."""
    sym = symbol.upper()
    entry, opened = entry_of(fills, sym)
    if entry is None:
        _marks.pop(sym, None)
        return None
    row = _marks.get(sym)
    if row is None or row.get("opened") != opened:
        row = _marks[sym] = {"entry": entry, "opened": opened, "stack": None, "at": now, "breakeven": False}
    row["entry"] = entry                          # an add moves the average
    if row["stack"] is None:
        row["stack"] = bid_stack(book)
    return row


def forget_except(symbols: set[str]) -> None:
    """A position gone flat leaves its mark and its retry clock."""
    for sym in [s for s in _marks if s not in symbols]:
        _marks.pop(sym, None)
        _fired_at.pop(sym, None)


def due(symbol: str, now: float) -> bool:
    """Not inside the wait after a close the door refused."""
    return now - _fired_at.get(symbol.upper(), -1e18) >= AGENT_GUARD_RETRY_SEC


def note_fired(symbol: str, now: float) -> None:
    _fired_at[symbol.upper()] = now


def judge(row: dict[str, Any], *, book: dict[str, Any] | None, prints: list[dict[str, Any]], now: float,
          l1_bid: float | None = None) -> str | None:
    """Why the guard sells now, in words, or None."""
    buy, sell = reflexes.flow(prints, now - AGENT_GUARD_SELLERS_SECONDS)
    if sell >= AGENT_GUARD_SELLERS_MIN_SHARES and sell >= AGENT_GUARD_SELLERS_RATIO * max(buy, 1.0):
        return (f"sellers lead: {sell:,.0f} shares hit the bid in {AGENT_GUARD_SELLERS_SECONDS:g} s against "
                f"{buy:,.0f} at the ask")
    stack, then = bid_stack(book), row.get("stack")
    if stack is not None and then and stack < float(then) * AGENT_GUARD_BID_STACK_FRACTION:
        return (f"the bids left: the top {AGENT_GUARD_BID_LEVELS} bid prices hold {stack:,.0f} shares, under a third "
                f"of the {float(then):,.0f} at entry")
    bid, entry = best_bid(book, l1_bid), float(row["entry"])
    if bid is not None and bid <= entry * (1.0 - AGENT_GUARD_BID_UNDER_ENTRY_PCT / 100.0) + 1e-9:
        return (f"the bid is {(1.0 - bid / entry) * 100.0:.2f}% under entry ({bid:g} against {entry:.4g})")
    return None


def first_half_sold(fills: list[dict[str, Any]], symbol: str, since: float | None) -> bool:
    """A pop exit's first half (the ``target`` leg) filled since the position opened."""
    sym = symbol.upper()
    return any(str(r.get("symbol") or "").upper() == sym and r.get("leg_role") == "target"
               and float(r.get("fill_ts") or 0.0) >= float(since or 0.0) for r in fills)
