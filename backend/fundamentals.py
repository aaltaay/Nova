"""yfinance fundamentals fetch + TTL cache.

Extracted from main.py so ticker fundamentals (float, short interest, splits,
etc.) stay out of the app entry point. Split calendar dates are formatted in
UTC — local-tz fromtimestamp was off-by-one for Yahoo epoch midnights
(e.g. LVLU 1:15 showing 2025-07-06 ET instead of trading-effective 2025-07-07).
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import yfinance as yf

from constants import FUNDAMENTALS_CACHE_TTL, YFINANCE_TIMEOUT_S

logger = logging.getLogger(__name__)

_fundamentals_cache: dict[str, dict] = {}
_fundamentals_cache_ts: dict[str, float] = {}

_EMPTY: dict = {
    "market_cap": None,
    "shares_outstanding": None,
    "float_shares": None,
    "short_interest": None,
    "short_ratio": None,
    "short_percent_of_float": None,
    "pe_ratio": None,
    "forward_pe": None,
    "eps": None,
    "sector": None,
    "industry": None,
    "fifty_two_week_high": None,
    "fifty_two_week_low": None,
    "dividend_yield": None,
    "beta": None,
    "earnings_date": None,
    "recent_split": None,
    "average_volume": None,
    "current_volume": None,
}


def _yf_date_str(raw) -> str | None:
    """Format a yfinance date (pandas Timestamp or epoch seconds) as YYYY-MM-DD in UTC."""
    if raw is None:
        return None
    try:
        if hasattr(raw, "strftime"):
            tz = getattr(raw, "tz", None) or getattr(raw, "tzinfo", None)
            if tz is not None and hasattr(raw, "tz_convert"):
                return raw.tz_convert("UTC").strftime("%Y-%m-%d")
            if tz is not None and hasattr(raw, "astimezone"):
                return raw.astimezone(timezone.utc).strftime("%Y-%m-%d")
            return raw.strftime("%Y-%m-%d")
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


def format_recent_split(split_factor, split_date) -> str | None:
    """Combine yfinance lastSplitFactor + lastSplitDate for the quote card."""
    if not split_factor:
        return None
    if not split_date:
        return str(split_factor)
    date_str = _yf_date_str(split_date)
    if date_str:
        return f"{split_factor} ({date_str})"
    return str(split_factor)


def fetch_fundamentals(symbol: str) -> dict:
    """Fetch fundamental data for a single symbol via yfinance with TTL caching."""
    now = time.monotonic()
    cached_ts = _fundamentals_cache_ts.get(symbol, 0.0)
    if symbol in _fundamentals_cache and (now - cached_ts) < FUNDAMENTALS_CACHE_TTL:
        return _fundamentals_cache[symbol]
    try:
        # yfinance has no built-in timeout; a stalled Yahoo request can block for 15-20s.
        # Run it in a dedicated thread so we can cap the wait at YFINANCE_TIMEOUT_S.
        with ThreadPoolExecutor(max_workers=1) as yf_pool:
            future = yf_pool.submit(lambda: yf.Ticker(symbol).info)
            try:
                info = future.result(timeout=YFINANCE_TIMEOUT_S)
            except Exception:
                stale = _fundamentals_cache.get(symbol)
                if stale is not None:
                    logger.warning("yfinance timeout/error for %s — returning stale cache", symbol)
                    return stale
                raise

        earnings_date: str | None = None
        raw_ed = info.get("earningsDate") or info.get("earningsTimestamp")
        if raw_ed is not None:
            try:
                if isinstance(raw_ed, (list, tuple)) and len(raw_ed) > 0:
                    raw_ed = raw_ed[0]
                earnings_date = _yf_date_str(raw_ed)
            except Exception:
                earnings_date = None

        fundamentals = {
            "market_cap": info.get("marketCap"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "float_shares": info.get("floatShares"),
            "short_interest": info.get("sharesShort"),
            "short_ratio": info.get("shortRatio"),
            "short_percent_of_float": info.get("shortPercentOfFloat"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "eps": info.get("trailingEps"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "earnings_date": earnings_date,
            "recent_split": format_recent_split(
                info.get("lastSplitFactor"),
                info.get("lastSplitDate"),
            ),
            "average_volume": info.get("averageVolume"),
            "current_volume": info.get("volume"),
        }
        _fundamentals_cache[symbol] = fundamentals
        _fundamentals_cache_ts[symbol] = now
        return fundamentals
    except Exception:
        empty = dict(_EMPTY)
        _fundamentals_cache[symbol] = empty
        _fundamentals_cache_ts[symbol] = now
        return empty


def fetch_fundamentals_batch(symbols: list[str]) -> None:
    """Populate the fundamentals cache for symbols (skips fresh cache hits)."""
    now = time.monotonic()
    missing = [
        s for s in symbols
        if s not in _fundamentals_cache
        or (now - _fundamentals_cache_ts.get(s, 0.0)) >= FUNDAMENTALS_CACHE_TTL
    ]
    for sym in missing:
        fetch_fundamentals(sym)


# Names used by main.py / hod_momo_enrichment during the incremental extract.
_fetch_fundamentals = fetch_fundamentals
_fetch_fundamentals_batch = fetch_fundamentals_batch
