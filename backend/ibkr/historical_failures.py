"""What IBKR last failed to answer, per (symbol, timeframe) (#555, ADR 012).

A historical fetch that times out or errors stores and pushes nothing, so the
chart pane only knew it was still "filling". This module remembers the last
failure for a short window so that:

- ``chart_bars`` can state it in ``/bars`` coverage (``last_error`` /
  ``last_error_ts``), and the pane says IBKR is not answering instead of
  "Loading";
- ``historical_service`` does not send the same pair again within
  ``IBKR_HISTORICAL_FAILURE_BACKOFF_SEC``, sparing the 60 / 10 min budget while
  IBKR's historical farm is down.

A success clears the pair at once. Written on the IB loop, read from HTTP
worker threads, so every access holds one small lock. No I/O.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from constants import (
    IBKR_HISTORICAL_FAILURE_BACKOFF_SEC,
    IBKR_HISTORICAL_FAILURE_MEMORY_SEC,
    IBKR_HISTORICAL_FAILURE_STATUSES,
)

_lock = threading.Lock()
# (SYMBOL, timeframe) -> (epoch seconds, detail)
_failures: dict[tuple[str, str], tuple[float, str]] = {}


def _now() -> float:
    return time.time()


def _key(symbol: str, timeframe: str) -> tuple[str, str]:
    return (symbol.upper(), timeframe)


def reset() -> None:
    with _lock:
        _failures.clear()


def remembered(status_code: int) -> bool:
    """Whether a fetch that failed with this HTTP status is IBKR not answering."""
    return int(status_code) in IBKR_HISTORICAL_FAILURE_STATUSES


def note(symbol: str, timeframe: str, detail: str) -> None:
    """Record a failed fetch for the pair now (replaces the previous one)."""
    now = _now()
    cutoff = now - float(IBKR_HISTORICAL_FAILURE_MEMORY_SEC)
    with _lock:
        for key in [k for k, (ts, _) in _failures.items() if ts < cutoff]:
            del _failures[key]
        _failures[_key(symbol, timeframe)] = (now, str(detail))


def clear(symbol: str, timeframe: str) -> None:
    """A successful fetch: the pair has no failure to state."""
    with _lock:
        _failures.pop(_key(symbol, timeframe), None)


def _current(symbol: str, timeframe: str, now: float) -> tuple[float, str] | None:
    with _lock:
        entry = _failures.get(_key(symbol, timeframe))
    if entry is None or now - entry[0] > float(IBKR_HISTORICAL_FAILURE_MEMORY_SEC):
        return None
    return entry


def backoff_remaining(symbol: str, timeframe: str) -> float:
    """Seconds before the pair may be sent again after a failure; 0 means now."""
    now = _now()
    entry = _current(symbol, timeframe, now)
    if entry is None:
        return 0.0
    return max(0.0, entry[0] + float(IBKR_HISTORICAL_FAILURE_BACKOFF_SEC) - now)


def coverage_fields(symbol: str, timeframe: str) -> dict[str, Any]:
    """``{last_error, last_error_ts}`` for bars coverage; both null when none."""
    entry = _current(symbol, timeframe, _now())
    if entry is None:
        return {"last_error": None, "last_error_ts": None}
    ts, detail = entry
    return {"last_error": detail, "last_error_ts": round(ts, 3)}
