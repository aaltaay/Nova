"""One symbol's facts for the "Why it's moving" read (ADR 028). No network wait.

The symbol's scanner row when a board holds it (surfaced as the Scanner shows it: float, RVOL, the
catalyst verdict), else its live L1 quote. Asked for one board's row (``board``, the Catalyst column) the read
takes that row at the price the board shows -- a frozen Gappers row reads its own +56%, not the trade an hour
later -- and names the L1 line's last trade beside it (``last_trade``); otherwise a row is repriced by that
trade (``with_live_trade``, the Trader card). ``priced_by`` says which; Yahoo fundamentals from the cache (a symbol not cached yet is
read in the background, and its split / short facts stay unknown meanwhile); an 8-K of the last 30 days that
says shares were issued (``catalysts/issuance.py``); today's halts from the
leaderboard's halt log (ADR 023), with a halt from the prior exchange day still in force when today began
(``carried``: a 19:50 news halt that resumes at 09:00 holds the whole premarket); borrow from the recorded IBKR file (``borrow_feed``). A fact nobody
holds is ``None`` -- unknown, never zero.

Owner: this module (no state of its own apart from the set of background reads in flight).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from constants_move_reason import (
    MOVE_LULD_HALT_KINDS,
    MOVE_NEWS_HALT_CODES,
    MOVE_PRICED_BY_BOARD_ROW,
    MOVE_PRICED_BY_LAST_TRADE,
    MOVE_PRICED_BY_QUOTE,
    MOVE_PRICED_BY_ROW,
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


def gather(symbol: str, now: float | None = None, board: str | None = None,
           halts: dict[str, Any] | None = None) -> dict[str, Any]:
    """``board`` reads that board's row at its own price (the Catalyst column); ``halts`` is the halt count when
    the caller read the log for many symbols at once (``halts_many``)."""
    now = time.time() if now is None else now
    sym = (symbol or "").strip().upper()
    from strategy.symbol_pillars import SOURCE_QUOTE

    row, source, priced_by, last_trade = _row(sym, board)
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
        "board": source if source != SOURCE_QUOTE else None,
        "priced_by": priced_by,
        "last_trade": last_trade,
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
        "halts": halts if halts is not None else halts_today(sym, now),
        "borrow": _borrow(sym, now),
        "catalyst": row.get("catalyst") if isinstance(row.get("catalyst"), dict) else None,
        "shares_issued": _shares_issued(sym),
        **_fund(fund),
    }


def _fund(fund: dict[str, Any] | None) -> dict[str, Any]:
    """Yahoo's ``quote_type`` (None while unknown) and, for a fund, what its name says it tracks (ADR 028 amendment 4)."""
    from move_reason import fund as fund_mod

    quote_type = (fund or {}).get("quote_type") or None
    if not fund_mod.is_fund(quote_type):
        return {"quote_type": quote_type, "fund": None}
    return {"quote_type": quote_type, "fund": fund_mod.from_name(fund.get("company_name"))}


def _shares_issued(sym: str) -> dict[str, Any] | None:
    """The newest 8-K of the last 30 days that says shares were issued (``catalysts/issuance.py``, in memory):
    Yahoo's float and share count predate it. None when none is on file."""
    from catalysts import issuance

    return issuance.for_symbol(sym)


def _row(sym: str, board: str | None = None) -> tuple[dict[str, Any], str, str, dict[str, Any] | None]:
    """The row, where it came from, which price it carries, and the L1 line's last trade when that is not it."""
    from scanner_surface import surface_rows
    from strategy.symbol_pillars import SOURCE_QUOTE, find_board_row, live_quote, quote_row, raw_boards, with_catalyst

    boards = raw_boards()
    quote = live_quote(sym)
    raw, source, last_trade = None, None, None
    if board:
        raw = next((r for r in boards.get(board) or () if str(r.get("symbol") or "").upper() == sym), None)
        source = board if raw is not None else None
    if raw is not None:
        priced_by = MOVE_PRICED_BY_BOARD_ROW
        last_trade = trade_of(raw, quote)
    else:
        raw, source = find_board_row(sym, boards)
        if raw is None:
            raw, source, priced_by = quote_row(sym, quote), SOURCE_QUOTE, MOVE_PRICED_BY_QUOTE
        else:
            repriced = with_live_trade(raw, quote)
            priced_by = MOVE_PRICED_BY_LAST_TRADE if repriced is not raw else MOVE_PRICED_BY_ROW
            raw = repriced
    try:
        surfaced = surface_rows([raw]) or [dict(raw)]
    except Exception:
        logger.warning("move_reason: surfacing %s failed; reading its raw row", sym, exc_info=True)
        surfaced = [dict(raw)]
    return with_catalyst(surfaced[0]), source or SOURCE_QUOTE, priced_by, last_trade


def trade_of(row: dict[str, Any], quote: dict[str, Any] | None) -> dict[str, Any] | None:
    """The L1 line's last trade against the row's previous close: ``{price, change_pct, ts}``, or None when the
    line holds no trade (IBKR's prior close before the first trade is not one, #541). Pure."""
    q = quote or {}
    price, ts = _num(q.get("price")), _num(q.get("last_trade_ts"))
    if price is None or price <= 0 or q.get("quote_quality") == "close_fallback" or ts is None:
        return None
    prev = _num(row.get("prev_close")) or _num(q.get("prev_close"))
    return {"price": price, "change_pct": price / prev - 1.0 if prev else None, "ts": ts}


def with_live_trade(row: dict[str, Any], quote: dict[str, Any] | None) -> dict[str, Any]:
    """The board row with its price and change taken from the live L1 line's last trade.

    A board stops repricing a row when its session ends (the Gainers row of a stock running after hours
    kept its 16:00 price), so a trade the L1 line has seen is the price. IBKR's prior close before the
    first trade (``close_fallback``, #541) is not a trade and changes nothing. Pure."""
    q = quote or {}
    price = _num(q.get("price"))
    if price is None or price <= 0 or q.get("quote_quality") == "close_fallback" or q.get("last_trade_ts") is None:
        return row
    out = dict(row)
    out["price"] = price
    prev = _num(row.get("prev_close")) or _num(q.get("prev_close"))
    out["change_pct"] = price / prev - 1.0 if prev else row.get("change_pct")
    vol = _num(q.get("volume"))
    if vol is not None and vol > (_num(row.get("volume")) or 0):
        out["volume"] = int(vol)
    return out


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


def _one_source(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nasdaq's list and IBKR's tick 49 see the same halts: one source, Nasdaq's when it has rows."""
    return [e for e in events if e.get("source") == _RSS_SOURCE] or list(events)


def _kind(e: dict[str, Any]) -> str:
    code, kind = str(e.get("code") or "").upper(), str(e.get("kind") or "")
    if code in MOVE_NEWS_HALT_CODES:
        return "news"
    if kind in MOVE_LULD_HALT_KINDS or code in MOVE_LULD_HALT_KINDS:
        return "luld"
    if code in MOVE_VOLATILITY_HALT_CODES:
        return "volatility"
    return "other"


def _ts(e: dict[str, Any]) -> float:
    return float(e.get("ts") or 0)


def count_halts(events: list[dict[str, Any]], prior: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Today's halt starts by kind, from one source, and ``carried``: the prior exchange day's halt still in
    force when today began (``prior`` is that day's log)."""
    rows = _one_source(events)
    out: dict[str, Any] = {"news": 0, "luld": 0, "volatility": 0, "other": 0,
                           "source": rows[0].get("source") if rows else None}
    for e in rows:
        if e.get("event") == "start":
            out[_kind(e)] += 1
    out["carried"] = _carried(_one_source(prior or []), events)
    return out


def _carried(before: list[dict[str, Any]], today: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The prior day's last halt when nothing that day ended it (FMFC: T1 at Oct 12 19:50, resumed Oct 13 09:00).
    ``resumed`` is the same source's first event today when that is an end; a start first means the log
    missed the end, and ``resumed`` stays None with ``still_halted`` false."""
    starts = [e for e in before if e.get("event") == "start"]
    if not starts:
        return None
    last = max(starts, key=_ts)
    if any(e.get("event") == "end" and _ts(e) >= _ts(last) for e in before):
        return None
    same = sorted((e for e in today if e.get("source") == last.get("source")), key=_ts)
    first = same[0] if same else None
    resumed = _ts(first) if first is not None and first.get("event") == "end" else None
    return {"kind": _kind(last), "code": str(last.get("code") or "").upper() or None, "source": last.get("source"),
            "since": _ts(last), "resumed": resumed, "still_halted": first is None}


def _halt_days(now: float) -> tuple[str, str]:
    """Today's date and the prior exchange day's, as the halt log keys them."""
    from sim.trading_day import last_open_day

    today = datetime.fromtimestamp(now, ET).date()
    return today.isoformat(), last_open_day(today - timedelta(days=1)).isoformat()


def halts_many(symbols: list[str], now: float) -> dict[str, dict[str, Any]] | None:
    """Today's halt counts for many symbols from one read of the log (the batch read); None when unreadable."""
    try:
        from leaderboard import store

        day, prior_day = _halt_days(now)
        with store.connect() as db:
            events = store.halt_events(db, day, until=now, symbols=list(symbols))
            prior = store.halt_events(db, prior_day, until=now, symbols=list(symbols))
    except Exception:
        logger.warning("move_reason: halt log unreadable for %d symbols", len(symbols), exc_info=True)
        return None
    by_sym: dict[str, list[dict[str, Any]]] = {s: [] for s in symbols}
    before: dict[str, list[dict[str, Any]]] = {s: [] for s in symbols}
    for rows, into in ((events, by_sym), (prior, before)):
        for e in rows:
            into.setdefault(str(e.get("symbol") or "").upper(), []).append(e)
    return {s: count_halts(by_sym.get(s) or [], before.get(s) or []) for s in symbols}


def halts_today(sym: str, now: float) -> dict[str, Any] | None:
    try:
        from leaderboard import store

        day, prior_day = _halt_days(now)
        with store.connect() as db:
            events = store.halt_events(db, day, until=now, symbols=[sym])
            prior = store.halt_events(db, prior_day, until=now, symbols=[sym])
    except Exception:
        logger.warning("move_reason: halt log unreadable for %s", sym, exc_info=True)
        return None
    return count_halts(events, prior)


def _borrow(sym: str, now: float) -> dict[str, Any] | None:
    try:
        from move_reason import borrow_feed

        if not borrow_feed.enabled():
            return None
        return borrow_feed.get_feed().view(sym, now)
    except Exception:
        logger.warning("move_reason: borrow view failed for %s", sym, exc_info=True)
        return None
