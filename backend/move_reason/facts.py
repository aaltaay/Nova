"""One symbol's facts for the "Why it's moving" read (ADR 028). No network wait.

The symbol's scanner row when a board holds it (surfaced as the Scanner shows it: float, RVOL, the
catalyst verdict), else its live L1 quote; Yahoo fundamentals from the cache (a symbol not cached yet is
read in the background, and its split / short facts stay unknown meanwhile); today's halts from the
leaderboard's halt log (ADR 023); borrow from the recorded IBKR file (``borrow_feed``). A fact nobody
holds is ``None`` -- unknown, never zero.

Owner: this module (no state of its own apart from the set of background reads in flight).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from constants_move_reason import (
    MOVE_LULD_HALT_KINDS,
    MOVE_NEWS_HALT_CODES,
    MOVE_VOLATILITY_HALT_CODES,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
_RSS_SOURCE = "nasdaq_trade_halt_rss"
_reading: set[str] = set()
_reading_lock = threading.Lock()


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if v == v else None


def gather(symbol: str, now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    sym = (symbol or "").strip().upper()
    row, source = _row(sym)
    fund = _fundamentals(sym)
    float_shares = _num(row.get("float")) or _num((fund or {}).get("float_shares"))
    si_from = row if row.get("short_interest") is not None else (fund or {})
    si = _num(si_from.get("short_interest"))
    # The surfaced row's own float check (#532); a row the surface could not decorate falls back to Yahoo's.
    checked = row if "float_contradicted" in row else (fund or {})
    contradicted = checked.get("float_contradicted")
    # More shares short than the float: a warning on the figures shown here, never a gate (#532).
    from fundamentals import short_above_float

    short_above, short_above_reason = short_above_float(float_shares, si)
    return {
        "symbol": sym,
        "source": source,
        "price": _num(row.get("price")),
        "change_pct": _num(row.get("change_pct")),
        "volume": _num(row.get("volume")),
        "rel_volume": _num(row.get("rel_volume")),
        "float_shares": float_shares,
        "float_contradicted": contradicted if isinstance(contradicted, bool) else None,
        "float_contradicted_reason": (checked.get("float_contradicted_reason") or None) if contradicted is True else None,
        "short_interest": si,
        # The FINRA settlement date of that figure, as Yahoo gives it (epoch seconds; None when unknown).
        "short_interest_ts": _num(si_from.get("short_interest_ts")) if si is not None else None,
        "short_above_float": short_above,
        "short_above_float_reason": short_above_reason,
        # Yahoo's own share only when the shares short or the float is missing (rules divide the two otherwise).
        "short_pct_float": None if si is not None and float_shares else _num((fund or {}).get("short_percent_of_float")),
        "days_to_cover": _num(row.get("short_ratio")) if row.get("short_ratio") is not None else _num((fund or {}).get("short_ratio")),
        "split": _split(fund, now),
        "halts": halts_today(sym, now),
        "borrow": _borrow(sym, now),
        "catalyst": row.get("catalyst") if isinstance(row.get("catalyst"), dict) else None,
    }


def _row(sym: str) -> tuple[dict[str, Any], str]:
    from scanner_surface import surface_rows
    from strategy.symbol_pillars import SOURCE_QUOTE, find_board_row, live_quote, quote_row, raw_boards, with_catalyst

    raw, source = find_board_row(sym, raw_boards())
    if raw is None:
        raw, source = quote_row(sym, live_quote(sym)), SOURCE_QUOTE
    try:
        surfaced = surface_rows([raw]) or [dict(raw)]
    except Exception:
        logger.warning("move_reason: surfacing %s failed; reading its raw row", sym, exc_info=True)
        surfaced = [dict(raw)]
    return with_catalyst(surfaced[0]), source or SOURCE_QUOTE


def _fundamentals(sym: str) -> dict[str, Any] | None:
    """The cached Yahoo row; None while unknown (not cached yet -- a background read is queued -- or failed)."""
    import fundamentals

    cached = fundamentals.peek_cached(sym)
    if cached is None:
        _read_in_background(sym)
        return None
    return None if fundamentals.fetch_failed(sym) else cached


def _read_in_background(sym: str) -> None:
    with _reading_lock:
        if sym in _reading:
            return
        _reading.add(sym)

    def work() -> None:
        try:
            import fundamentals

            fundamentals.fetch_fundamentals(sym)
        except Exception:
            logger.warning("move_reason: fundamentals read failed for %s", sym, exc_info=True)
        finally:
            with _reading_lock:
                _reading.discard(sym)

    threading.Thread(target=work, daemon=True, name=f"move_reason_fund_{sym}").start()


def _split(fund: dict[str, Any] | None, now: float) -> dict[str, Any] | None:
    if fund is None:
        return None
    factor = fund.get("last_split_factor")
    if not factor:
        return {"factor": None, "ts": None, "reverse": None, "days_ago": None}
    ts = _num(fund.get("last_split_ts"))
    a, _, b = str(factor).partition(":")
    try:
        reverse = float(a) < float(b)
    except ValueError:
        reverse = None
    return {"factor": str(factor), "ts": ts, "reverse": reverse,
            "days_ago": (now - ts) / 86400 if ts is not None else None}


def count_halts(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Halt starts by kind. Nasdaq's list and IBKR's tick 49 see the same halts: count one source,
    Nasdaq's when it has any rows for the symbol."""
    rss = [e for e in events if e.get("source") == _RSS_SOURCE]
    rows = rss or events
    out = {"news": 0, "luld": 0, "volatility": 0, "other": 0, "source": _RSS_SOURCE if rss else (
        rows[0].get("source") if rows else None)}
    for e in rows:
        if e.get("event") != "start":
            continue
        code, kind = str(e.get("code") or "").upper(), str(e.get("kind") or "")
        if code in MOVE_NEWS_HALT_CODES:
            out["news"] += 1
        elif kind in MOVE_LULD_HALT_KINDS or code in MOVE_LULD_HALT_KINDS:
            out["luld"] += 1
        elif code in MOVE_VOLATILITY_HALT_CODES:
            out["volatility"] += 1
        else:
            out["other"] += 1
    return out


def halts_today(sym: str, now: float) -> dict[str, Any] | None:
    try:
        from leaderboard import store

        day = datetime.fromtimestamp(now, ET).date().isoformat()
        with store.connect() as db:
            events = store.halt_events(db, day, until=now, symbols=[sym])
    except Exception:
        logger.warning("move_reason: halt log unreadable for %s", sym, exc_info=True)
        return None
    return count_halts(events)


def _borrow(sym: str, now: float) -> dict[str, Any] | None:
    try:
        from move_reason import borrow_feed

        if not borrow_feed.enabled():
            return None
        return borrow_feed.get_feed().view(sym, now)
    except Exception:
        logger.warning("move_reason: borrow view failed for %s", sym, exc_info=True)
        return None
