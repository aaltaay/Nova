"""Recorded Level 2 for the one historical replay surface (#309, ADR 017).

``backend/sim/history_*`` stays the only replay engine, store and selection
state. This module is just the pipe that lets a book already recorded by
``backend/l2/`` reach that engine's snapshot, so depth surfaces through the
replay UI the operator already has instead of a second scrubber.

**Nothing here invents a book.** An IBKR historical download carries trades
only, and ``l2.db`` holds short-lived hot sessions, so the common answer is
"not recorded" -- returned as ``None`` and rendered as a plain statement, never
as an empty or fabricated ladder.

Precedence: a loaded capture owns depth on its own path
(``sim.capture_player.book_at``, injected by ``sim.feed``), and selecting a
historical window clears the capture selection, so the two never answer the
same playhead. ``l2.db`` fills exactly the sessions no tab recording covered.

Cost: the replay snapshot is polled while scrubbing, so the lookup is bounded
to one indexed newest-at-or-before row per replayed second, memoized in a small
map. The playhead is floored to its second before the read, which also makes
lookahead impossible. A missing, locked or damaged ``l2.db`` degrades to "not
recorded" and is reported once per outage, never per poll, and never raised
into the replay.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections import OrderedDict

from constants_sim import (
    SIM_HISTORY_DEPTH_CACHE_ENTRIES, SIM_HISTORY_DEPTH_MAX_AGE_SEC, SIM_HISTORY_DEPTH_SOURCE,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
# (symbol, replayed second) -> resolved book or None. Bounded; a scrub simply
# evicts the oldest entries.
_cache: "OrderedDict[tuple[str, int], dict | None]" = OrderedDict()
# Last archive failure already reported, so an unreadable l2.db logs once per
# outage instead of once per poll. Cleared by the next successful read.
_degraded: str | None = None


def clear() -> None:
    """Drop memoized books. Called on selection change, which is this desk's
    explicit "reload from the archive" gesture, so a session recorded since the
    last selection becomes visible without a restart."""
    global _degraded
    with _lock:
        _cache.clear()
        _degraded = None


def reset_for_tests() -> None:
    clear()


def _cached(key: tuple[str, int]) -> tuple[bool, dict | None]:
    with _lock:
        if key not in _cache:
            return False, None
        _cache.move_to_end(key)
        return True, _cache[key]


def _remember(key: tuple[str, int], book: dict | None) -> None:
    with _lock:
        _cache[key] = book
        _cache.move_to_end(key)
        while len(_cache) > SIM_HISTORY_DEPTH_CACHE_ENTRIES:
            _cache.popitem(last=False)


def _report(error: Exception | None) -> None:
    """One log line per archive outage, and one when it clears."""
    global _degraded
    signature = f"{type(error).__name__}: {error}" if error is not None else None
    with _lock:
        if signature == _degraded:
            return
        previous, _degraded = _degraded, signature
    if signature is None:
        logger.info("Replay depth: recorded Level 2 archive is readable again (was %s)", previous)
    else:
        logger.warning("Replay depth: recorded Level 2 unavailable; replay continues "
                       "without a book", exc_info=error)


def _read(symbol: str, second: int) -> dict | None:
    """One archive read. Imported lazily: l2 is an optional feeder, and the
    replay engine must stay importable without it."""
    from l2 import recall

    row = recall.book_before(symbol, float(second), SIM_HISTORY_DEPTH_MAX_AGE_SEC)
    if row is None:
        return None
    return {
        "symbol": row["symbol"],
        "bids": list(row["bids"] or []),
        "asks": list(row["asks"] or []),
        "ts": float(row["ts"]),
        "age_sec": round(second - float(row["ts"]), 3),
        "l1_fallback": bool(row["l1_fallback"]),
        "session_id": row.get("session_id"),
        "source": SIM_HISTORY_DEPTH_SOURCE,
    }


def book_at(symbol: str, playhead_ts: float) -> dict | None:
    """The recorded book at ``playhead_ts``, or ``None`` when none was recorded.

    Callers must treat ``None`` as "depth was not recorded for this moment",
    which is a fact about the archive, not an error.
    """
    key = (symbol.upper(), int(playhead_ts))
    hit, cached = _cached(key)
    if hit:
        return cached
    try:
        book = _read(*key)
    except (sqlite3.Error, OSError, ImportError, json.JSONDecodeError,
            ValueError, TypeError, KeyError) as exc:
        _report(exc)
        _remember(key, None)
        return None
    _report(None)
    _remember(key, book)
    return book
