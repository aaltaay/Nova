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

from bot.live_trader.constants_live_trader import LT_QUOTE_FRESH_SEC

logger = logging.getLogger(__name__)
_CAP_RETRY_SEC = 120.0

_lock = threading.Lock()
_cap_reads: dict[str, float] = {}           # symbol -> when its read began (one read at a time per symbol)


def reset_for_tests() -> None:
    with _lock:
        _cap_reads.clear()


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
    return {"last": _num(last), "bid": _num(bid) or _num(l1_bid), "ask": _num(ask) or _num(l1_ask),
            "fresh": bool(fresh)}


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out > 0 else None


def cap(symbol: str) -> Any:
    """The market cap in dollars, ``"pending"`` while it is read, None when it could not be read."""
    import fundamentals

    sym = (symbol or "").strip().upper()
    cached = fundamentals.peek_cached(sym)
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
