"""Real aggressor sides for historical prints -- from the local L2 recording, or none.

An IBKR historical download carries trades only, so on its own the replay tape
cannot say whether a print hit the bid or lifted the ask, and it says nothing
(AGENTS.md §3). ``l2.db`` often holds the answer: ``backend/l2/`` samples the
book about once a second while a depth session is open. This module uses it --
but only where it actually decides the question.

A print's timestamp is a whole second, so the print happened somewhere in
[S, S+1). Its side is known only if the quote held across that whole span: a
recorded book at or before S, one at or after S+1 (each within
``SIM_HISTORY_DEPTH_MAX_AGE_SEC``), and every book between them with the same
top of book. Then the live tape's own rule classifies it (``ibkr/tape_side``),
so a replayed print is coloured exactly as the live tape would have coloured it.
Anything short of that -- a quote change inside the span, a gap in the
recording, a crossed book, an unreported print -- stays ``None``. Nothing is
inferred from price movement.

Cost and failure: memoized per (symbol, second), so a tape re-polled every
second reads only the seconds it has not seen; a missing or unreadable
``l2.db`` means "not recorded" and never reaches the replay as an error.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections import OrderedDict

from constants_sim import (
    SIM_HISTORY_DEPTH_MAX_AGE_SEC, SIM_HISTORY_SIDE_CACHE_ENTRIES, SIM_HISTORY_SIDE_SOURCE,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
# (symbol, second) -> (bid, ask) that held across [second, second + 1), or None.
_cache: "OrderedDict[tuple[str, int], tuple[float, float] | None]" = OrderedDict()
_degraded = False


def clear() -> None:
    """Forget memoized quotes; called with every selection change, like depth."""
    global _degraded
    with _lock:
        _cache.clear()
        _degraded = False


def reset_for_tests() -> None:
    clear()


def _top(book: dict) -> tuple[float, float] | None:
    from ibkr.tape_side import best_bid_ask
    bid, ask = best_bid_ask(book)
    return (bid, ask) if bid is not None and ask is not None else None


def steady_quote(books: list[dict], second: int) -> tuple[float, float] | None:
    """The top of book if it provably held across [second, second + 1), else None.

    ``books`` are oldest first and cover [second - max_age, second + 1 + max_age].
    """
    before = [b for b in books if float(b["ts"]) <= second]
    after = [b for b in books if float(b["ts"]) >= second + 1]
    if not before or not after:
        return None
    span = [b for b in books if float(before[-1]["ts"]) <= float(b["ts"]) <= float(after[0]["ts"])]
    tops = {_top(b) for b in span}
    if len(tops) != 1:
        return None
    (top,) = tops
    return top


def _read(symbol: str, second: int) -> tuple[float, float] | None:
    from l2.store import get_snapshots_between
    books = get_snapshots_between(symbol, second - SIM_HISTORY_DEPTH_MAX_AGE_SEC,
                                  second + 1 + SIM_HISTORY_DEPTH_MAX_AGE_SEC)
    return steady_quote(books, second)


def _quote(symbol: str, second: int) -> tuple[float, float] | None:
    global _degraded
    key = (symbol, second)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    try:
        quote = _read(symbol, second)
    except (sqlite3.Error, OSError, ImportError, json.JSONDecodeError,
            ValueError, TypeError, KeyError) as exc:
        with _lock:
            first = not _degraded
            _degraded = True
        if first:
            logger.warning("Replay sides: recorded L2 unavailable; prints stay uncoloured", exc_info=exc)
        return None
    with _lock:
        _cache[key] = quote
        while len(_cache) > SIM_HISTORY_SIDE_CACHE_ENTRIES:
            _cache.popitem(last=False)
    return quote


def attach_recorded_sides(symbol: str, prints: list[dict]) -> int:
    """Set side/bid/ask on prints the recording decides; return how many."""
    from ibkr.tape_side import TAPE_SIDE_UNKNOWN, classify_print_side
    sym = symbol.upper()
    decided = 0
    for row in prints:
        row.update(side=None, bid=None, ask=None, side_source=None)
        if row.get("unreported"):
            continue
        quote = _quote(sym, int(row["ts"]))
        if quote is None:
            continue
        side = classify_print_side(row["price"], *quote)
        if side == TAPE_SIDE_UNKNOWN:
            continue
        row.update(side=side, bid=quote[0], ask=quote[1], side_source=SIM_HISTORY_SIDE_SOURCE)
        decided += 1
    return decided
