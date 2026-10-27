"""The market the Live Trader bot reads: a stock's quote, its market cap, the short hours. Memory reads.

``quote`` is the stock's IBKR Level 1 line (``ibkr.ticks``, the line ``lines`` holds for the bot), its bid and ask
from Nova's book when a Level 2 line is open: the same live feed Paper fills against. ``cap`` is Yahoo's market cap
through ``fundamentals`` -- a cached read, else ``"pending"`` while a background read runs (``want_caps``), else
None when Yahoo did not answer: an unknown cap is a stated skip, never a guess. Shapes:
architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from collections import deque

from bot.live_trader import feed_rows
from bot.live_trader.constants_live_trader import LT_PRICE_KEEP_SEC, LT_QUOTE_FRESH_SEC

logger = logging.getLogger(__name__)
_CAP_RETRY_SEC = 120.0

_lock = threading.Lock()
_cap_reads: dict[str, float] = {}           # symbol -> when its read began (one read at a time per symbol)
_prices: dict[str, deque] = {}              # symbol -> (ts, market) each pass, ``LT_PRICE_KEEP_SEC`` (memory only)


def reset_for_tests() -> None:
    with _lock:
        _cap_reads.clear()
        _prices.clear()


def note_prices(symbols: set[str], now: float) -> None:
    """Sample each stock's market now (its fresh quote's mid, else last), for ``range_since``."""
    for sym in symbols:
        q = quote(sym) or {}
        ref = feed_rows.reference_price(q) if q.get("fresh") else None
        with _lock:
            kept = _prices.setdefault(sym, deque())
            if ref is not None:
                kept.append((now, float(ref)))
            while kept and now - kept[0][0] > LT_PRICE_KEEP_SEC:
                kept.popleft()
            if not kept:
                _prices.pop(sym, None)


def range_since(symbol: str, since: float) -> tuple[float, float] | None:
    """``(low, high)`` of the market sampled from ``since`` on, or None when the samples do not reach back to it."""
    with _lock:
        kept = list(_prices.get((symbol or "").strip().upper()) or ())
    if not kept or kept[0][0] > since:
        return None
    seen = [p for ts, p in kept if ts >= since] or [kept[-1][1]]
    return min(seen), max(seen)


def quote(symbol: str) -> dict[str, Any] | None:
    """``{last, bid, ask, fresh}`` from the stock's live line, or None without one. ``fresh``: the line moved
    within ``LT_QUOTE_FRESH_SEC`` and its last is a trade, not IBKR's prior close."""
    from constants import IBKR_QUOTE_QUALITY_CLOSE_FALLBACK
    from ibkr import ticks
    from ibkr.depth import state as depth_state
    from practice.reference import top_of_book

    sym = (symbol or "").strip().upper()
    try:
        row = ticks.last_quotes([sym]).get(sym)
        if not row:
            return None
        bid, ask = top_of_book(depth_state.current_book(sym))
        l1_bid, l1_ask = ticks.bid_ask(sym)
        fresh = ticks.is_fresh(sym, LT_QUOTE_FRESH_SEC)
    except Exception:
        logger.warning("Live Trader bot: %s's quote could not be read", sym, exc_info=True)
        return None
    last = row.get("price")
    if row.get("quote_quality") == IBKR_QUOTE_QUALITY_CLOSE_FALLBACK:
        last, fresh = None, False
    traded = row.get("last_trade_ts")
    return {"last": _num(last), "bid": _num(bid) or _num(l1_bid), "ask": _num(ask) or _num(l1_ask),
            "fresh": bool(fresh), "last_ts": float(traded) if isinstance(traded, (int, float)) else None}


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out > 0 else None


def ssr(symbol: str) -> str:
    """The stock's SSR now, ``"on"`` | ``"off"`` | ``"unknown"`` (``short_sale.ssr.live``, the short check's own
    read), asking IBKR for its daily bars when due. Unknown counts as on: the short is priced above the bid."""
    from short_sale import ssr as _ssr

    sym = (symbol or "").strip().upper()
    try:
        _ssr.request_history(sym, urgent=True)
        return _ssr.live(sym).state
    except Exception:  # noqa: BLE001 -- an unread SSR is unknown, which prices the short as if SSR were on
        logger.warning("Live Trader: SSR for %s not read", sym, exc_info=True)
        return "unknown"


def cap(symbol: str) -> Any:
    """The market cap in dollars, ``"etf"`` for an ETF (always allowed, operator 2026-10-14), ``"pending"`` while
    it is read, None when it could not be read."""
    import fundamentals

    sym = (symbol or "").strip().upper()
    cached = fundamentals.peek_cached(sym)
    if cached is not None and str(cached.get("quote_type") or "").upper() == "ETF":
        return "etf"
    if cached is not None and _num(cached.get("market_cap")) is not None:
        return float(cached["market_cap"])
    if fundamentals.fetch_failed(sym) or (cached is not None and cached.get("market_cap") is None):
        return None
    return "pending"


def want_caps(symbols: set[str] | list[str]) -> None:
    """Read the market caps not known yet, each on its own thread, at most every ``_CAP_RETRY_SEC``."""
    import fundamentals

    now = time.time()
    for sym in sorted({(s or "").strip().upper() for s in symbols if s}):
        if fundamentals.peek_cached(sym) is not None:
            continue
        with _lock:
            began = _cap_reads.get(sym)
            if began is not None and now - began < _CAP_RETRY_SEC:
                continue
            _cap_reads[sym] = now
        threading.Thread(target=_read_cap, args=(sym,), name=f"live-trader-cap-{sym}", daemon=True).start()


def _read_cap(symbol: str) -> None:
    import fundamentals

    try:
        fundamentals.fetch_fundamentals(symbol)
    except Exception:
        logger.warning("Live Trader bot: %s's market cap could not be read", symbol, exc_info=True)


def short_closed(now: float) -> str | None:
    """Why no new short may open at ``now`` (09:35 to 15:50 ET by the venue's clock), or None."""
    from short_sale.hours import entry_refusal

    return entry_refusal(now)


def cover_ts(now: float) -> float | None:
    """Today's day cover (15:55, 12:55 on an early close): from then Nova's day cover covers every Paper short."""
    from short_sale.hours import hours_on

    hours = hours_on(now)
    return hours.cover_ts if hours else None


def keep_borrow(symbols: set[str]) -> None:
    """Re-read IBKR's borrow of each stock before its read goes stale (``shortability.refresh_due``), as an open
    Trader tab does: every stock the bot holds short, so the host's add finds a fresh read for the short check."""
    try:
        from ibkr.shortability import cached, refresh_due, request_refresh
    except Exception:
        logger.warning("Live Trader bot: the borrow read is not available", exc_info=True)
        return
    for sym in sorted(symbols):
        try:
            snap = cached(sym)
            if snap is None or refresh_due(snap, float(snap.get("age_sec") or 0.0)):
                request_refresh(sym)
        except Exception:
            logger.warning("Live Trader bot: %s's borrow was not kept fresh", sym, exc_info=True)


def prewarm_borrow(symbols: set[str]) -> None:
    """Ask IBKR for the borrow of stocks the bot may short, so the short check finds it fresh."""
    try:
        from ibkr.shortability import request_refresh
    except Exception:
        logger.warning("Live Trader bot: the borrow read is not available", exc_info=True)
        return
    for sym in sorted(symbols):
        try:
            request_refresh(sym)
        except Exception:
            logger.warning("Live Trader bot: %s's borrow was not asked for", sym, exc_info=True)
