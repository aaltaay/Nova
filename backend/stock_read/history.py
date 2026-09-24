"""One symbol's history (ADR 036): its past runs from the stored daily bars, and what Nova holds on
it -- setups armed on any day, the Level 2 it recorded, the borrow file's changes, the latest short
interest -- with what Nova does not keep per symbol yet said so.

``runs`` is pure; ``summary`` caches the daily read per symbol and session day (it changes once a day).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from constants_stock_read import (
    STOCK_READ_HISTORY_CHART_DAYS,
    STOCK_READ_HISTORY_READ_DAYS,
    STOCK_READ_RUN_MIN_PCT,
    STOCK_READ_SETUPS_HISTORY_DAYS,
)
from stock_read.rows import row, shares

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
BORROW_HISTORY_DAYS = 14                  # the borrow store keeps this long (move_reason, MOVE_BORROW_RETENTION_DAYS)
_cache: dict[tuple[str, str], dict[str, Any]] = {}
_lock = threading.Lock()


def daily_bars(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stored daily bars (epoch ``t`` at the session's UTC midnight) as ``{d, o, h, l, c, v}``."""
    out = []
    for b in raw:
        d = datetime.fromtimestamp(float(b["t"]), timezone.utc).date().isoformat()
        out.append({"d": d, "o": float(b["o"]), "h": float(b["h"]), "l": float(b["l"]), "c": float(b["c"]),
                    "v": float(b.get("v") or 0)})
    return out


def runs(daily: list[dict[str, Any]], today: str | None) -> list[dict[str, Any]]:
    """Sessions whose high was ``STOCK_READ_RUN_MIN_PCT`` or more over the prior bar's close, newest
    first. Stored daily bars close on the last extended-hours trade, so both sides are the day's last
    trade, not the 16:00 close."""
    out = []
    for prev, b in zip(daily, daily[1:]):
        pc = prev["c"]
        if pc <= 0:
            continue
        run = b["h"] / pc - 1
        if run >= STOCK_READ_RUN_MIN_PCT:
            out.append({"date": b["d"], "prior_close": round(pc, 4), "high": round(b["h"], 4), "close": round(b["c"], 4),
                        "run_pct": round(run, 4), "close_pct": round(b["c"] / pc - 1, 4), "today": b["d"] == today})
    out.reverse()
    return out


def summary(symbol: str, now: float) -> dict[str, Any] | None:
    """``{daily, daily_days, runs}`` for the symbol, read once per session day."""
    from sensors.feeds import get_bars

    today = datetime.fromtimestamp(now, ET).date().isoformat()
    key = (symbol, today)
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    raw, _src = get_bars(symbol, "1Day", STOCK_READ_HISTORY_READ_DAYS)
    daily = daily_bars(raw)
    out = {"daily": daily[-STOCK_READ_HISTORY_CHART_DAYS:], "daily_days": len(daily), "runs": runs(daily, today)}
    with _lock:
        if len(_cache) > 256:
            _cache.clear()
        _cache[key] = out
    return out


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
