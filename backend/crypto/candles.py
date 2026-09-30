"""The Cryptos page's chart (ADR 040): a coin's Coinbase candles, the day's levels, and the US stock sessions.

``view`` answers from ``crypto.state`` only (the refresher reads Coinbase): the candles for the time frame, and
from the 15-minute series the 24-hour high and low, the last price and its 24-hour change, the crypto day's
open (00:00 UTC) and the price at the last 16:00 ET stock close. Sessions are drawn for the intraday frames.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from constants import (
    SESSION_AFTERHOURS_END_MIN_ET,
    SESSION_PREMARKET_START_MIN_ET,
    SESSION_RTH_CLOSE_MIN_ET,
    SESSION_RTH_OPEN_MIN_ET,
)
from constants_crypto import (
    CRYPTO_CANDLES_SHOWN,
    CRYPTO_CANDLES_TTL_SEC,
    CRYPTO_COINS,
    CRYPTO_HOURLY_TTL_SEC,
    CRYPTO_SCHEMA_VERSION,
)
from crypto import clock
from crypto.coinbase import price_at
from crypto.state import Store

COIN_BY_SYMBOL = {c["symbol"]: c for c in CRYPTO_COINS}
_SESSIONS = (
    ("premarket", SESSION_PREMARKET_START_MIN_ET, SESSION_RTH_OPEN_MIN_ET),
    ("regular", SESSION_RTH_OPEN_MIN_ET, SESSION_RTH_CLOSE_MIN_ET),
    ("after_hours", SESSION_RTH_CLOSE_MIN_ET, SESSION_AFTERHOURS_END_MIN_ET),
)
_INTRADAY = ("15m", "1h")


def view(st: Store, symbol: str, tf: str, now: float) -> dict:
    coin = COIN_BY_SYMBOL[symbol]
    key = f"candles:{symbol}:{tf}"
    series = st.get(key, now, CRYPTO_CANDLES_TTL_SEC[tf])
    result = st.result(key)
    failed = result is not None and not result[1]
    candles = (series or [])[-CRYPTO_CANDLES_SHOWN:]
    s15 = st.get(f"candles:{symbol}:15m", now, CRYPTO_CANDLES_TTL_SEC["15m"]) or []
    hourly = st.get(f"hourly:{symbol}", now, CRYPTO_HOURLY_TTL_SEC) or []
    return {
        "schema_version": CRYPTO_SCHEMA_VERSION,
        "symbol": symbol,
        "tf": tf,
        "product": coin["coinbase"],
        "source": "coinbase",
        "loading": series is None and not failed,
        "error": result[3] if failed else None,
        "candles": candles,
        **levels(s15, hourly, now),
        "sessions": sessions(candles, tf) if tf in _INTRADAY else [],
    }


def levels(s15: list[dict], hourly: list[dict], now: float) -> dict:
    """``last``, ``change_24h_pct`` and ``levels`` from the 15-minute series (``None`` where it has no answer)."""
    window = [c for c in s15 if c["t"] + 900 > now - 86400]
    last = s15[-1]["c"] if s15 else None
    start = window[0]["o"] if window else None
    day_at = clock.crypto_day_start(now)
    ref_at, _ = clock.reference_close(now)
    close_px = price_at(s15, ref_at, 900)
    if close_px is None:
        close_px = price_at(hourly, ref_at, 3600)
    return {
        "last": last,
        "change_24h_pct": (last / start - 1) * 100 if last is not None and start else None,
        "levels": {
            "high_24h": max((c["h"] for c in window), default=None),
            "low_24h": min((c["l"] for c in window), default=None),
            "day_open": price_at(s15, day_at, 900),
            "day_open_at": day_at,
            "stock_close": {"at": ref_at, "price": close_px} if close_px is not None else None,
        },
    }


def sessions(candles: list[dict], tf: str) -> list[dict]:
    """The US stock sessions (premarket / regular / after hours) that overlap the candles' span."""
    if not candles:
        return []
    step = 900 if tf == "15m" else 3600
    lo, hi = candles[0]["t"], candles[-1]["t"] + step
    day = datetime.fromtimestamp(lo, clock.ET).date()
    last_day = datetime.fromtimestamp(hi, clock.ET).date()
    out = []
    while day <= last_day:
        if clock.open_day(day):
            for kind, a, b in _SESSIONS:
                start = datetime(day.year, day.month, day.day, a // 60, a % 60, tzinfo=clock.ET).timestamp()
                end = datetime(day.year, day.month, day.day, b // 60, b % 60, tzinfo=clock.ET).timestamp()
                if end > lo and start < hi:
                    out.append({"kind": kind, "start": max(start, lo), "end": min(end, hi)})
        day += timedelta(days=1)
    return out
