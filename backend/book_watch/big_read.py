"""The big-seller reading (#846), one shape for ``GET /api/book-watch/{symbol}/big-sellers`` and
``/sensors/big-sellers``: the live line's (``live.big_reading``), or on a Sim replay the loaded Session
Record's at the playhead (``big_replay``).

Never a guess: with no depth line, a line that has sent no book for ``BOOK_WATCH_IDLE_SEC``, the watcher
off, or a replay with no recorded book there, ``watching`` is false, ``reason`` says why in plain words,
and no price is listed -- an absence, never "no big seller". Read-only: nothing here places, gates or
cancels an order.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from book_watch import big_replay, live
from book_watch.big_seller import DEFAULT_BIG
from book_watch.constants_book_watch import (
    BOOK_WATCH_BIG_NOTE,
    BOOK_WATCH_IDLE_SEC,
    BOOK_WATCH_OFF_REASON,
    BOOK_WATCH_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)


def rule() -> dict[str, Any]:
    p = DEFAULT_BIG
    return {"min_shares": p.min_shares, "min_dollars": p.min_dollars, "median_mult": p.median_mult,
            "min_other_levels": p.min_other_levels, "min_hold_sec": p.min_hold_sec,
            "window_dollars": p.window_dollars, "window_pct": p.window_pct, "window_max_pct": p.window_max_pct,
            "taken_share": p.taken_share, "show_ended_sec": p.show_ended_sec}


def _base(symbol: str, source: str, as_of: float) -> dict[str, Any]:
    return {"schema_version": BOOK_WATCH_SCHEMA_VERSION, "symbol": symbol, "source": source,
            "as_of": round(as_of, 3), "rule": rule(), "note": BOOK_WATCH_BIG_NOTE}


def _absent(symbol: str, source: str, as_of: float, reason: str, **extra: Any) -> dict[str, Any]:
    return {**_base(symbol, source, as_of), "watching": False, "reason": reason, "sellers": [], "buyers": [],
            **extra}


def _stale(symbol: str, age: float | None, *, recorded: bool) -> str:
    what = "The recording holds" if recorded else f"The Level 2 line for {symbol} has sent"
    if age is None:
        return f"{what} no book yet: no read on big sellers or buyers until it does."
    when = "before the playhead" if recorded else "now"
    return (f"{what} no book for {age:.0f} s {when}: a book older than {BOOK_WATCH_IDLE_SEC:g} s is not "
            "read, so there is no read on big sellers or buyers.")


def _replay_desk() -> bool:
    from sim.mode import is_replay_desk

    try:
        return bool(is_replay_desk())
    except Exception:
        logger.warning("big sellers: the Sim live edge is unreadable -- the desk counts as a replay", exc_info=True)
        return True


def live_reading(symbol: str, now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    if not live.enabled():
        return _absent(symbol, "live", now, BOOK_WATCH_OFF_REASON)
    got = live.big_reading(symbol, now)
    if got is None:
        return _absent(symbol, "live", now, (
            f"No Level 2 line for {symbol} has reached the book watcher: Nova sees a big seller only on a depth "
            "line it holds (at most 3). Open its Level 2."))
    if not got["watching"]:
        return _absent(symbol, "live", now, _stale(symbol, got["last_book_age_sec"], recorded=False),
                       last_book_age_sec=got["last_book_age_sec"])
    return {**_base(symbol, "live", now), "reason": None, **got}


def replay_reading(symbol: str) -> dict[str, Any]:
    from sim import capture_player

    playhead = capture_player.asof_unix()
    data = capture_player.snapshot()
    if data is None or str(data.symbol).upper() != symbol:
        return _absent(symbol, "replay", playhead, (
            f"On a Sim replay Nova reads big sellers from a Session Record of {symbol} (its recorded Level 2 and "
            "tape); none is loaded."))
    if not data.l2:
        return _absent(symbol, "replay", playhead, f"The loaded Session Record of {symbol} kept no Level 2 book.")
    if not capture_player.covered(playhead, state=data):
        return _absent(symbol, "replay", playhead, "The playhead is between recorded stretches: nothing was "
                       "recorded here.")
    got = big_replay.reading(data, playhead)
    if not got["watching"]:
        return _absent(symbol, "replay", playhead, _stale(symbol, got["last_book_age_sec"], recorded=True),
                       last_book_age_sec=got["last_book_age_sec"])
    return {**_base(symbol, "replay", playhead), "reason": None, **got}


def reading(symbol: str) -> dict[str, Any]:
    """The reading for ``symbol`` on this desk: the replay's on a Sim replay, else the live line's."""
    sym = (symbol or "").strip().upper()
    return replay_reading(sym) if _replay_desk() else live_reading(sym)
