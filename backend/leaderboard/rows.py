"""The leaderboard row (AGENTS.md section 3) -- pure builders, no I/O.

``make_row`` is the one constructor: recorded rows come through
``from_desk_row`` and the offline rebuild calls ``make_row`` directly, so both
sources land in the store in one shape with every unknown as ``None``.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

from constants_leaderboard import (
    LEADERBOARD_BOARDS,
    LEADERBOARD_RVOL_BASES,
    LEADERBOARD_RVOL_BASIS_DAILY,
    LEADERBOARD_SOURCES,
)

ET = ZoneInfo("America/New_York")
_CLOSE_FALLBACK = "close_fallback"


def num(value: Any) -> float | None:
    """A finite number or None -- bools, strings and NaN are unknowns."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    return out if isfinite(out) else None


def positive(value: Any) -> float | None:
    out = num(value)
    return out if out is not None and out > 0 else None


def session_date_for(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), ET).date().isoformat()


def change_fraction(price: float | None, prev_close: float | None) -> float | None:
    """Price against the prior close, as a fraction; None when either is unknown."""
    if price is None or prev_close is None:
        return None
    return (price - prev_close) / prev_close


def make_row(
    *,
    symbol: str,
    minute_ts: int,
    board: str,
    source: str,
    rank: int,
    price: Any = None,
    prev_close: Any = None,
    volume: Any = None,
    rvol: Any = None,
    rvol_basis: str | None = None,
    float_shares: Any = None,
    has_news: bool | None = None,
    news_first_seen_ts: Any = None,
    gap_pct: Any = None,
    exchange: str | None = None,
    market_cap: Any = None,
    float_contradicted: bool | None = None,
    shares_outstanding: Any = None,
) -> dict[str, Any]:
    if board not in LEADERBOARD_BOARDS:
        raise ValueError(f"unknown leaderboard board {board!r}")
    if source not in LEADERBOARD_SOURCES:
        raise ValueError(f"unknown leaderboard source {source!r}")
    if int(minute_ts) % 60:
        raise ValueError(f"minute_ts {minute_ts} is not a whole minute")
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("leaderboard row without a symbol")
    price_v = positive(price)
    prev_v = positive(prev_close)
    rvol_v = num(rvol)
    basis = rvol_basis if rvol_v is not None else None
    if basis is not None and basis not in LEADERBOARD_RVOL_BASES:
        raise ValueError(f"unknown rvol basis {basis!r}")
    if rvol_v is not None and basis is None:
        raise ValueError("an rvol without its basis cannot be compared with anything")
    volume_v = num(volume)
    float_v = positive(float_shares)
    return {
        "session_date": session_date_for(minute_ts),
        "minute_ts": int(minute_ts),
        "source": source,
        "board": board,
        "symbol": sym,
        "rank": int(rank),
        "price": price_v,
        "prev_close": prev_v,
        "change_pct": change_fraction(price_v, prev_v),
        "volume": volume_v if volume_v is not None and volume_v >= 0 else None,
        "rvol": rvol_v,
        "rvol_basis": basis,
        "float_shares": float_v,
        "has_news": None if has_news is None else bool(has_news),
        "news_first_seen_ts": num(news_first_seen_ts),
        "gap_pct": num(gap_pct),
        "exchange": (exchange or None) if isinstance(exchange, str) else None,
        "market_cap": positive(market_cap),
        # The desk row's float check (#532): it describes the float beside it, so none without one.
        "float_contradicted": (float_contradicted if isinstance(float_contradicted, bool) and float_v is not None
                               else None),
        "shares_outstanding": positive(shares_outstanding),
    }


def headline_ts(row: Mapping[str, Any], minute_ts: int) -> float | None:
    """The row's ``newest_headline_at`` as epoch seconds, only when at or before the snapshot."""
    raw = row.get("newest_headline_at")
    ts = num(raw)
    if ts is None and isinstance(raw, str):
        try:
            ts = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            ts = None
    if ts is not None and ts > 10_000_000_000:  # milliseconds
        ts /= 1000.0
    return ts if ts is not None and ts <= minute_ts else None


def from_desk_row(
    row: Mapping[str, Any],
    *,
    minute_ts: int,
    board: str,
    rank: int,
    news_first_seen_ts: float | None = None,
) -> dict[str, Any]:
    """A surfaced scanner row (``scanner_surface.surface_rows``) as a recorded row.

    A ``close_fallback`` row carries IBKR's prior close with no print yet:
    its price is not a price, so price and change are recorded as unknown.
    ``news_first_seen_ts`` is the caller's earliest headline time seen for the
    symbol that day (the desk row only names its newest headline).
    ``float_contradicted`` / ``shares_outstanding`` are the row's float check
    (#532, ``mover_enrich_view``), kept so ``LEADERS_RULES`` reads them later.
    """
    no_print = row.get("quote_quality") == _CLOSE_FALLBACK
    price = None if no_print else (row.get("price") if row.get("price") is not None else row.get("current_price"))
    prev_close = row.get("prev_close") if row.get("prev_close") is not None else row.get("previous_close")
    rvol = row.get("rel_volume")
    has_news = row.get("has_news")
    return make_row(
        symbol=str(row.get("symbol") or ""),
        minute_ts=minute_ts,
        board=board,
        source="recorded",
        rank=rank,
        price=price,
        prev_close=prev_close,
        volume=row.get("volume"),
        rvol=rvol,
        rvol_basis=LEADERBOARD_RVOL_BASIS_DAILY if num(rvol) is not None else None,
        float_shares=row.get("float") if row.get("float") is not None else row.get("float_shares"),
        has_news=has_news if isinstance(has_news, bool) else None,
        news_first_seen_ts=news_first_seen_ts,
        gap_pct=row.get("gap_percent"),
        exchange=row.get("exchange"),
        market_cap=row.get("market_cap"),
        float_contradicted=row.get("float_contradicted"),
        shares_outstanding=row.get("shares_outstanding"),
    )
