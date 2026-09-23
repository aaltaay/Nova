"""The halt / LULD event log (ADR 022). Enqueue-only; safe on the IB loop.

Two real sources, each logged under its own name: IBKR ``ticker.halted``
(incoming tick type 49) transitions observed by ``ibkr.halt_status``, and the
Nasdaq Trade Halt RSS rows (official start and resume times). A halt is never
inferred from quiet tape. An event already logged is not enqueued again; the
store's primary key makes a repeat harmless anyway.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable, Mapping
from typing import Any

from constants_leaderboard import (
    LEADERBOARD_HALT_EVENT_END,
    LEADERBOARD_HALT_EVENT_START,
    LEADERBOARD_HALT_SOURCE_IBKR,
    LEADERBOARD_HALT_SOURCE_NASDAQ,
)
from leaderboard import queue
from leaderboard.rows import num, session_date_for

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_seen: set[tuple[str, str, str, float]] = set()
_SEEN_MAX = 50_000


def event(
    *,
    symbol: str,
    ts: float,
    kind: str,
    source: str,
    halt_kind: str | None = None,
    code: Any = None,
    recorded_ts: float | None = None,
) -> dict[str, Any] | None:
    """One halt_events row, or None for an event without a symbol or a time."""
    sym = (symbol or "").strip().upper()
    when = num(ts)
    if not sym or when is None or kind not in (LEADERBOARD_HALT_EVENT_START, LEADERBOARD_HALT_EVENT_END):
        return None
    return {
        "symbol": sym,
        "ts": float(when),
        "event": kind,
        "kind": halt_kind,
        "code": None if code is None else str(code),
        "source": source,
        "session_date": session_date_for(when),
        "recorded_ts": time.time() if recorded_ts is None else float(recorded_ts),
    }


def _enqueue_new(rows: Iterable[dict[str, Any] | None]) -> int:
    fresh: list[dict[str, Any]] = []
    with _lock:
        for row in rows:
            if row is None:
                continue
            key = (row["symbol"], row["source"], row["event"], row["ts"])
            if key in _seen:
                continue
            if len(_seen) >= _SEEN_MAX:
                _seen.clear()
            _seen.add(key)
            fresh.append(row)
    queue.enqueue("halts", fresh)
    return len(fresh)


def observe_ibkr(symbol: str, snapshot: Mapping[str, Any] | None, *, now: float | None = None) -> int:
    """A ``halt_status.observe_code`` transition: a snapshot starts a halt, None ends one."""
    ts = time.time() if now is None else float(now)
    if snapshot:
        row = event(
            symbol=symbol,
            ts=num(snapshot.get("halt_start")) or ts,
            kind=LEADERBOARD_HALT_EVENT_START,
            source=LEADERBOARD_HALT_SOURCE_IBKR,
            halt_kind=snapshot.get("kind"),
            code=snapshot.get("halt_code"),
        )
    else:
        row = event(symbol=symbol, ts=ts, kind=LEADERBOARD_HALT_EVENT_END, source=LEADERBOARD_HALT_SOURCE_IBKR)
    return _enqueue_new([row])


def observe_rss(rows: Iterable[Any]) -> int:
    """Every parsed Nasdaq Trade Halt RSS row (``HaltRssRow``): its official start and resume."""
    out: list[dict[str, Any] | None] = []
    for row in rows:
        symbol = getattr(row, "symbol", None)
        if not symbol or getattr(row, "mwcb_level", None) is not None:
            continue
        reason = getattr(row, "reason_code", None)
        start = getattr(row, "official_halt_start", None)
        resume = getattr(row, "trade_resume", None)
        if start is not None:
            out.append(event(
                symbol=symbol, ts=start, kind=LEADERBOARD_HALT_EVENT_START,
                source=LEADERBOARD_HALT_SOURCE_NASDAQ, halt_kind=reason, code=reason,
            ))
        if resume is not None:
            out.append(event(
                symbol=symbol, ts=resume, kind=LEADERBOARD_HALT_EVENT_END,
                source=LEADERBOARD_HALT_SOURCE_NASDAQ, halt_kind=reason, code=reason,
            ))
    return _enqueue_new(out)


def halted_at(events: Iterable[Mapping[str, Any]], symbol: str, ts: float) -> bool:
    """True while the newest logged event at or before ``ts`` for ``symbol`` is a start."""
    latest: Mapping[str, Any] | None = None
    for row in events:
        if row.get("symbol") != symbol or float(row.get("ts") or 0) > ts:
            continue
        if latest is None or float(row["ts"]) >= float(latest["ts"]):
            latest = row
    return latest is not None and latest.get("event") == LEADERBOARD_HALT_EVENT_START


def reset_for_tests() -> None:
    with _lock:
        _seen.clear()
