"""One symbol's history (ADR 036): its past runs from the stored daily bars, and what Nova holds on
it -- setups armed on any day, the Level 2 it recorded, the borrow file's changes, the latest short
interest -- with what Nova does not keep per symbol yet said so.

``runs`` is pure; ``summary`` caches the daily read per symbol and session day, until a fill writes that
symbol's daily bars again (``bars_store.daily_revision``).

Each daily bar carries its ``state`` (``bars_store.daily_bar_state``, #839): only a ``final`` one is the
finished session. A past bar stored before its session ended (``partial``) or with no record of when
(``unknown``) is listed in ``unfinished``, reads in no run or 200-day average, and asks the paced
background fill for the finished day; a cached read holding one is read again after the repair's retry.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from itertools import pairwise
from typing import Any
from zoneinfo import ZoneInfo

from constants_stock_read import (
    STOCK_READ_DAILY_SMA_DAYS,
    STOCK_READ_HISTORY_CHART_DAYS,
    STOCK_READ_HISTORY_READ_DAYS,
    STOCK_READ_RUN_MIN_PCT,
    STOCK_READ_SETUPS_HISTORY_DAYS,
)
from market import session_key_et
from stock_read.rows import row, shares

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
BORROW_HISTORY_DAYS = 14                  # the borrow store keeps this long (move_reason, MOVE_BORROW_RETENTION_DAYS)
# (symbol, session day, replay) -> {"out", "rev": the symbol's daily revision, "until": monotonic expiry or None}
_cache: dict[tuple[str, str, bool], dict[str, Any]] = {}
_lock = threading.Lock()


def daily_bars(raw: list[dict[str, Any]], now: float | None = None) -> list[dict[str, Any]]:
    """Stored daily bars (epoch ``t`` at the session's UTC midnight) as ``{d, o, h, l, c, v, state, through}``:
    ``state`` against wall-clock ``now`` (``bars_store.daily_bar_state``; ``final`` without ``now``, for
    bars that carry no provenance), ``through`` when a fill stored it (epoch seconds, None if not known)."""
    from bars_store import daily_bar_state

    out = []
    for b in raw:
        d = datetime.fromtimestamp(float(b["t"]), timezone.utc).date().isoformat()
        w = b.get("w")
        state = "final" if now is None else daily_bar_state(b["t"], w, now)
        out.append({"d": d, "o": float(b["o"]), "h": float(b["h"]), "l": float(b["l"]), "c": float(b["c"]),
                    "v": float(b.get("v") or 0), "state": state, "through": w})
    return out


def runs(daily: list[dict[str, Any]], today: str | None) -> list[dict[str, Any]]:
    """Sessions whose high was ``STOCK_READ_RUN_MIN_PCT`` or more over the prior bar's close, newest
    first. Stored daily bars close on the last extended-hours trade, so both sides are the day's last
    trade, not the 16:00 close. Only a finished prior close counts, and only a finished session (or
    today's, still forming) can be a run: a stored snapshot is neither the day's high nor its close."""
    out = []
    for prev, b in pairwise(daily):
        if prev.get("state", "final") != "final" or b.get("state", "final") not in ("final", "forming"):
            continue
        pc = prev["c"]
        if pc <= 0:
            continue
        run = b["h"] / pc - 1
        if run >= STOCK_READ_RUN_MIN_PCT:
            out.append({"date": b["d"], "prior_close": round(pc, 4), "high": round(b["h"], 4), "close": round(b["c"], 4),
                        "run_pct": round(run, 4), "close_pct": round(b["c"] / pc - 1, 4), "today": b["d"] == today})
    out.reverse()
    return out


def summary(symbol: str, now: float, *, replay: bool = False) -> dict[str, Any] | None:
    """``{daily, daily_days, runs, sma200, unfinished}`` for the symbol, read once per session day.
    ``sma200`` is the mean of the last 200 stored daily closes before today (None with fewer, or when one
    of them is not a finished session): the Full Day chart's level. ``daily_days`` counts finished
    sessions; ``unfinished`` lists the past ones that are not (``{date, state, stored_through}``).
    ``replay``: ``now`` is a Sim replay's playhead (ADR 052) -- only the days before the replayed one are read,
    never its own daily bar (the whole day's high) or a later day's; whether a bar is finished is still
    judged against the wall clock, when the store wrote it."""
    import bars_store
    from constants import IBKR_BARS_DAILY_REPAIR_RETRY_SEC
    from sensors.feeds import get_bars

    today = session_key_et(datetime.fromtimestamp(now, ET))   # the session on screen: weekends and 00:00-04:00 included
    key = (symbol, today, replay)
    rev = bars_store.daily_revision(symbol)
    with _lock:
        hit = _cache.get(key)
    if hit is not None and hit["rev"] == rev and (hit["until"] is None or time.monotonic() < hit["until"]):
        return hit["out"]
    raw, _src = get_bars(symbol, "1Day", STOCK_READ_HISTORY_READ_DAYS, provenance=True)
    daily = daily_bars(raw, time.time() if replay else now)
    if replay:
        daily = [b for b in daily if b["d"] < today]
    past = [b for b in daily if b["d"] < today]
    last200 = past[-STOCK_READ_DAILY_SMA_DAYS:]
    sma200 = (round(sum(b["c"] for b in last200) / len(last200), 4)
              if len(last200) == STOCK_READ_DAILY_SMA_DAYS and all(b["state"] == "final" for b in last200) else None)
    unfinished = [{"date": b["d"], "state": b["state"], "stored_through": b["through"]}
                  for b in past if b["state"] != "final"]
    out = {"daily": daily[-STOCK_READ_HISTORY_CHART_DAYS:],
           "daily_days": sum(1 for b in daily if b["state"] == "final"), "runs": runs(daily, today),
           "sma200": sma200, "unfinished": unfinished}
    if unfinished:
        _repair(symbol)
    with _lock:
        if len(_cache) > 256:
            _cache.clear()
        _cache[key] = {"out": out, "rev": rev,
                       "until": time.monotonic() + float(IBKR_BARS_DAILY_REPAIR_RETRY_SEC) if unfinished else None}
    return out


def daily_note(hist: dict[str, Any] | None) -> str | None:
    """The daily map's note on the past sessions that are not finished in the store, or None."""
    gone = (hist or {}).get("unfinished") or []
    if not gone:
        return None
    last = gone[-1]
    when = datetime.fromisoformat(last["date"])
    day = f"{when.strftime('%b')} {when.day}"
    if len(gone) > 1:
        what = f"{len(gone)} stored sessions are not finished (newest {day})"
    elif last["stored_through"] is not None:
        what = (f"{day} was stored at {datetime.fromtimestamp(last['stored_through'], ET):%H:%M} ET, "
                "before its session ended")
    else:
        what = f"{day} has no record of when it was stored"
    return f"{what}: not read as a finished day until IBKR's refetch lands"


def _repair(symbol: str) -> None:
    try:
        from ibkr import historical_service

        historical_service.schedule_daily_repair(symbol, STOCK_READ_HISTORY_READ_DAYS)
    except Exception:
        logger.warning("stock read history: the daily refetch of %s could not be asked", symbol, exc_info=True)


def holdings(symbol: str, now: float, why_facts: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    out.append(_safe("setups", lambda: _setups_armed(symbol, now)))
    out.append(_safe("l2", lambda: _l2_recorded(symbol, now)))
    out.append(row("boards", "Days on the boards", "Not kept per symbol yet", "unknown",
                   "The leaderboard store", "It keeps every minute's boards, with no per-symbol index yet."))
    out.append(_safe("borrow", lambda: _borrow_history(symbol, now)))
    si = (why_facts or {}).get("short_interest")
    out.append(row("short_interest", "Short interest", f"{shares(si)} shares (latest settlement only)" if si else "Unknown",
                   "info" if si else "unknown", "FINRA via Yahoo",
                   "Yahoo gives the latest settlement only; a trend needs FINRA's files."))
    return out


def _safe(name: str, fn) -> dict[str, Any]:
    try:
        return fn()
    except Exception as exc:
        logger.warning("stock read history: %s failed", name, exc_info=True)
        return row(name, name.title(), "Not known", "unknown", "--", f"{type(exc).__name__}: {exc}"[:160])


def _setups_armed(symbol: str, now: float) -> dict[str, Any]:
    from setup_scanner.engine import get_engine
    from setup_scanner.store import session_date

    store = get_engine().store
    src = "The setups scoreboard (every template)"
    if store is None:
        return row("setups", "Setups armed", "Not known", "unknown", src, "The scoreboard is not open")
    since = session_date(now - STOCK_READ_SETUPS_HISTORY_DAYS * 86400)
    rows = store.rows(date_from=since, symbol=symbol)
    if not rows:
        return row("setups", "Setups armed", f"None in {STOCK_READ_SETUPS_HISTORY_DAYS} days", "info", src)
    days = sorted({r.get("session_date") for r in rows if r.get("session_date")})
    trig = sum(1 for r in rows if r.get("triggered_at"))
    return row("setups", "Setups armed", f"{len(rows)} on {len(days)} day{'s' if len(days) != 1 else ''}, "
               f"{trig} triggered", "info", src, f"Last: {days[-1]}" if days else None)


def _l2_recorded(symbol: str, now: float) -> dict[str, Any]:
    from l2.sessions import get_sessions

    src = "The Level 2 archive (replay it in Sim)"
    sessions = get_sessions(symbol=symbol, limit=500)
    if not sessions:
        return row("l2", "Level 2 recorded", "None", "info", src)
    today = datetime.fromtimestamp(now, ET).date()
    mine = [s for s in sessions if datetime.fromtimestamp(float(s.get("started_ts") or 0), ET).date() == today]
    days = {datetime.fromtimestamp(float(s.get("started_ts") or 0), ET).date() for s in sessions}
    if mine:
        first = min(float(s["started_ts"]) for s in mine)
        value = f"Today from {datetime.fromtimestamp(first, ET):%H:%M}, {len(mine)} stretch{'es' if len(mine) != 1 else ''}"
    else:
        value = f"{len(days)} day{'s' if len(days) != 1 else ''} on file"
    return row("l2", "Level 2 recorded", value, "ok" if mine else "info", src)


def _borrow_history(symbol: str, now: float) -> dict[str, Any]:
    from move_reason import borrow_store

    src = f"IBKR's short-stock file, the last {BORROW_HISTORY_DAYS} days"
    db = borrow_store.connect()
    try:
        changes = borrow_store.changes_between(db, symbol, now - BORROW_HISTORY_DAYS * 86400, now)
    finally:
        db.close()
    if not changes:
        return row("borrow", "Borrow history", "No changes on file", "info", src)
    fees = [c["fee_rate"] for c in changes if c.get("fee_rate") is not None]
    dry = sum(1 for c in changes if not c["listed"] or not c.get("available"))
    return row("borrow", "Borrow history", f"{len(changes)} change{'s' if len(changes) != 1 else ''}"
               + (f", fee up to {max(fees):.1f}%/yr" if fees else "") + (f", nothing to lend {dry}x" if dry else ""),
               "info", src)
