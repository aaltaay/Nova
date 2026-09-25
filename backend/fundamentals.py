"""yfinance fundamentals fetch + TTL cache, and the float credibility check.

Extracted from main.py so ticker fundamentals (float, short interest, splits,
etc.) stay out of the app entry point. Split calendar dates are formatted in
UTC — local-tz fromtimestamp was off-by-one for Yahoo epoch midnights
(e.g. LVLU 1:15 showing 2025-07-06 ET instead of trading-effective 2025-07-07).

Yahoo's float is its last 10-Q / 10-K / 20-F cover count less insiders, blind
to any dilution since (#532). ``float_credibility`` flags a float that Yahoo's
own share counts contradict; every max-float gate reads the flag through
``strategy.float_gate`` (a contradicted float passes only on shares outstanding).
``short_above_float`` is a warning only: more shares short than the float holds
is what a stale float looks like, and also what a squeeze looks like.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import yfinance as yf

from constants import (
    FUNDAMENTALS_CACHE_MAX_ENTRIES,
    FUNDAMENTALS_CACHE_TTL,
    FUNDAMENTALS_NEGATIVE_CACHE_TTL,
    YFINANCE_TIMEOUT_S,
)
from constants_scanner import FUNDAMENTALS_FLOAT_MIN_NON_INSIDER_SHARE
from ibkr.errors import describe_exc

logger = logging.getLogger(__name__)

_fundamentals_cache: dict[str, dict] = {}
_fundamentals_cache_ts: dict[str, float] = {}
_fundamentals_cache_ttl: dict[str, float] = {}
_YF_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yf-fundamentals")

_EMPTY: dict = {
    "company_name": None,
    "market_cap": None,
    "shares_outstanding": None,
    "float_shares": None,
    "held_percent_insiders": None,
    "float_contradicted": None,
    "float_contradicted_reason": None,
    "short_interest": None,
    "short_interest_ts": None,
    "short_above_float": None,
    "short_above_float_reason": None,
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
    "earnings_ts": None,
    "earnings_estimated": None,
    "earnings_next_date": None,
    "recent_split": None,
    "last_split_factor": None,
    "last_split_ts": None,
    "average_volume": None,
    "current_volume": None,
}


def _yf_epoch(raw) -> int | None:
    """Coerce a Yahoo timestamp (int, float, or one-element list) to epoch seconds."""
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


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


def _positive(v) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if v == v and v > 0 else None


def _share_words(n: float) -> str:
    """54K, 8.45M, 1.20B: the count in the reason a contradicted float gives."""
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if n >= 1e6:
        return f"{n / 1e6:.2f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}K"
    return f"{n:.0f}"


def _pct_words(frac: float) -> str:
    return f"{frac * 100:.1f}".removesuffix(".0") + "%"


def float_credibility(
    float_shares, shares_outstanding, held_percent_insiders,
) -> tuple[bool | None, str | None]:
    """Whether Yahoo's own share counts contradict its float (#532): ``(contradicted, reason)``.

    Contradicted when the float is under ``FUNDAMENTALS_FLOAT_MIN_NON_INSIDER_SHARE`` of the
    shares outstanding less insiders. ``True`` when that fires; ``False`` when it could be checked
    and did not; ``None`` (unknown) otherwise -- no float, or shares outstanding or insiders
    unknown. Every max-float gate reads this flag (``strategy.float_gate``). Short interest above
    the float is not part of it: that is ``short_above_float``, a warning no gate reads. Pure.
    """
    f = _positive(float_shares)
    if f is None:
        return None, None
    out = _positive(shares_outstanding)
    ins = held_percent_insiders
    if isinstance(ins, bool) or not isinstance(ins, (int, float)) or not 0 <= ins < 1:
        ins = None
    if out is None or ins is None:
        return None, None
    share = FUNDAMENTALS_FLOAT_MIN_NON_INSIDER_SHARE
    if f < share * out * (1 - ins):
        portion = "half" if share == 0.5 else _pct_words(share)
        return True, (
            f"Float {_share_words(f)} is under {portion} of the {_share_words(out * (1 - ins))} shares not held "
            f"by insiders ({_share_words(out)} outstanding, {_pct_words(ins)} insiders) -- likely stale since a dilution"
        )
    return False, None


def short_above_float(float_shares, short_interest) -> tuple[bool | None, str | None]:
    """Whether more shares are short than the float holds (#532): ``(above, reason)`` -- a warning.

    Either the float is stale, or shares were lent more than once, which is what a heavily shorted
    name looks like. The two cannot be told apart here, so no gate reads it; the desk shows it beside
    the short interest. ``True`` / ``False`` when both figures are known, ``None`` otherwise. Pure.
    """
    f = _positive(float_shares)
    si = short_interest
    if isinstance(si, bool) or not isinstance(si, (int, float)) or not si >= 0:
        si = None
    if f is None or si is None:
        return None, None
    if si <= f:
        return False, None
    return True, (
        f"Short interest {_share_words(si)} is above the {_share_words(f)} float -- either the float is stale "
        "or shares were lent more than once (heavy shorting). A warning only: no gate reads it"
    )


def _cache_ttl(symbol: str) -> float:
    return _fundamentals_cache_ttl.get(symbol, FUNDAMENTALS_CACHE_TTL)


def _is_fresh(symbol: str, now: float) -> bool:
    if symbol not in _fundamentals_cache:
        return False
    return (now - _fundamentals_cache_ts.get(symbol, 0.0)) < _cache_ttl(symbol)


def _is_negative_cache(symbol: str) -> bool:
    return _fundamentals_cache_ttl.get(symbol) == FUNDAMENTALS_NEGATIVE_CACHE_TTL


def _drop_cache(symbol: str) -> None:
    _fundamentals_cache.pop(symbol, None)
    _fundamentals_cache_ts.pop(symbol, None)
    _fundamentals_cache_ttl.pop(symbol, None)


def peek_cached(symbol: str) -> dict | None:
    """Cache-only fundamentals row. Never hits Yahoo."""
    key = (symbol or "").strip().upper()
    row = _fundamentals_cache.get(key)
    return dict(row) if row else None


def fetch_failed(symbol: str) -> bool:
    """True when the cached row is the placeholder of a failed Yahoo read (every field unknown)."""
    return _is_negative_cache((symbol or "").strip().upper())


def cache_size() -> int:
    return len(_fundamentals_cache)


def evict_stale(now: float, keep: str | None = None) -> None:
    """Drop expired keys, then LRU-cap the rest (D-024)."""
    for sym in list(_fundamentals_cache):
        if sym == keep:
            continue
        if not _is_fresh(sym, now):
            _drop_cache(sym)
    max_n = max(1, int(FUNDAMENTALS_CACHE_MAX_ENTRIES))
    while len(_fundamentals_cache) > max_n:
        candidates = [s for s in _fundamentals_cache if s != keep]
        if not candidates:
            break
        oldest = min(candidates, key=lambda s: _fundamentals_cache_ts.get(s, 0.0))
        _drop_cache(oldest)


def _store_cache(symbol: str, payload: dict, now: float, ttl: float) -> dict:
    _fundamentals_cache[symbol] = payload
    _fundamentals_cache_ts[symbol] = now
    _fundamentals_cache_ttl[symbol] = ttl
    evict_stale(now, keep=symbol)
    return payload


def fetch_fundamentals(symbol: str) -> dict:
    """Fetch fundamental data for a single symbol via yfinance with TTL caching."""
    now = time.monotonic()
    if _is_fresh(symbol, now):
        return _fundamentals_cache[symbol]
    try:
        # yfinance has no built-in timeout; a stalled Yahoo request can block for 15-20s.
        # Reuse one worker so a Yahoo stall does not spawn a thread per symbol.
        future = _YF_POOL.submit(lambda: yf.Ticker(symbol).info)
        try:
            info = future.result(timeout=YFINANCE_TIMEOUT_S)
        except Exception:
            stale = _fundamentals_cache.get(symbol)
            if stale is not None and not _is_negative_cache(symbol):
                logger.warning(
                    "yfinance timeout/error for %s -- returning stale cache",
                    symbol,
                )
                return stale
            raise

        from earnings_window import earnings_date_et

        earnings_ts = _yf_epoch(info.get("earningsTimestamp"))
        earnings_date = earnings_date_et(earnings_ts)
        earnings_next_date = earnings_date_et(
            _yf_epoch(info.get("earningsTimestampStart") or info.get("earningsTimestampEnd"))
        )
        estimated = info.get("isEarningsDateEstimate")
        if estimated is not None:
            estimated = bool(estimated)

        contradicted, contradicted_reason = float_credibility(
            info.get("floatShares"), info.get("sharesOutstanding"), info.get("heldPercentInsiders"),
        )
        short_above, short_above_reason = short_above_float(info.get("floatShares"), info.get("sharesShort"))
        fundamentals = {
            "company_name": info.get("longName") or info.get("shortName"),
            "market_cap": info.get("marketCap"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "float_shares": info.get("floatShares"),
            # A fraction (0.128 = 12.8%), as Yahoo gives it.
            "held_percent_insiders": info.get("heldPercentInsiders"),
            "float_contradicted": contradicted,
            "float_contradicted_reason": contradicted_reason,
            "short_interest": info.get("sharesShort"),
            # The FINRA settlement date Yahoo's short interest is from (epoch seconds, UTC midnight).
            "short_interest_ts": _yf_epoch(info.get("dateShortInterest")),
            # A warning, never a gate: a stale float, or shares lent more than once.
            "short_above_float": short_above,
            "short_above_float_reason": short_above_reason,
            # Yahoo's own ratio: short interest over Yahoo's average volume, not FINRA's days to cover.
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
            "earnings_ts": earnings_ts,
            "earnings_estimated": estimated,
            "earnings_next_date": earnings_next_date,
            "recent_split": format_recent_split(
                info.get("lastSplitFactor"),
                info.get("lastSplitDate"),
            ),
            # Raw, for the "Why it's moving" read (ADR 028): "1:9" is a 1-for-9 reverse split.
            "last_split_factor": info.get("lastSplitFactor"),
            "last_split_ts": _yf_epoch(info.get("lastSplitDate")),
            "average_volume": info.get("averageVolume"),
            "current_volume": info.get("volume"),
        }
        return _store_cache(symbol, fundamentals, now, FUNDAMENTALS_CACHE_TTL)
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", symbol, describe_exc(exc))
        return _store_cache(symbol, dict(_EMPTY), now, FUNDAMENTALS_NEGATIVE_CACHE_TTL)


def fetch_fundamentals_batch(symbols: list[str]) -> None:
    """Populate the fundamentals cache for symbols (skips fresh cache hits)."""
    now = time.monotonic()
    evict_stale(now)
    missing = [s for s in symbols if not _is_fresh(s, now)]
    for sym in missing:
        fetch_fundamentals(sym)


# Names used by main.py / hod_momo_enrichment during the incremental extract.
_fetch_fundamentals = fetch_fundamentals
_fetch_fundamentals_batch = fetch_fundamentals_batch
