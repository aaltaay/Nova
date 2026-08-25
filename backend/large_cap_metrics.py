"""Pure swing metrics for the Large Cap table (ADR 014).

Every metric here is Nova's own design for a swing use case, not a Warrior
Trading parity target -- Warrior has no published swing criteria (see ADR
014 context). Split by cost:

- ``compute_rvol`` / ``days_to_earnings`` are zero-IB-cost: they read fields
  ``fundamentals.py`` already fetches via yfinance. Callers read the module
  cache dict directly (never call ``fetch_fundamentals`` -- that can block on
  a cold-cache yfinance round trip, which must never happen on the hot L1
  tick path).
- ``daily_bar_metrics`` reads ``bars_store`` (already-archived IBKR daily
  bars); a miss schedules a paced background fill (ADR 012) and returns
  ``None`` for every field so callers render a dash, never a fabricated
  zero. Results are TTL-cached in this module -- daily bars do not change
  intraday, so there is no reason to hit SQLite on every L1 tick.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

from constants import (
    LARGE_CAP_ATR_PERIOD,
    LARGE_CAP_DAILY_BARS_LOOKBACK,
    LARGE_CAP_DAILY_METRICS_TTL_SEC,
)

logger = logging.getLogger(__name__)

_daily_metrics_cache: dict[str, dict[str, Any]] = {}
_daily_metrics_cache_ts: dict[str, float] = {}

_EMPTY_DAILY: dict[str, Any] = {
    "atr14": None,
    "change_5d_pct": None,
    "change_20d_pct": None,
    "high_20d": None,
    "low_20d": None,
}


def compute_rvol(today_volume: float | None, average_volume: float | None) -> float | None:
    """Pace RVOL: today's volume vs. expected-by-now from the average."""
    import market

    return market.pace_relative_volume(today_volume, average_volume)


def days_to_earnings(earnings_date: str | None, *, today: date | None = None) -> int | None:
    if not earnings_date:
        return None
    try:
        d = datetime.strptime(str(earnings_date)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return (d - (today or date.today())).days


def _atr(bars: list[dict], *, period: int) -> float | None:
    """Simple average true range over the last *period* bars (no Wilder smoothing
    -- a plain average is legible and matches what one manual look at daily
    bars would compute)."""
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        high, low, prev_close = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    window = trs[-period:]
    return sum(window) / len(window) if window else None


def schedule_daily_fill(symbol: str) -> None:
    """Fire-and-forget background daily-bar fill (ADR 012). Never blocks."""
    try:
        from ibkr import historical_service

        historical_service.schedule_fill(
            symbol, "1Day", LARGE_CAP_DAILY_BARS_LOOKBACK + 1, priority="background",
        )
    except Exception:
        logger.debug("large_cap_metrics: schedule_fill failed for %s", symbol, exc_info=True)


def _compute_daily_bar_metrics(symbol: str) -> dict[str, Any]:
    import bars_store

    out = dict(_EMPTY_DAILY)
    stored = bars_store.read(symbol, "1Day", LARGE_CAP_DAILY_BARS_LOOKBACK + 1)
    bars = (stored or {}).get("bars") or []
    if len(bars) < 2:
        schedule_daily_fill(symbol)
        return out
    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    lookback_highs = highs[-LARGE_CAP_DAILY_BARS_LOOKBACK:]
    lookback_lows = lows[-LARGE_CAP_DAILY_BARS_LOOKBACK:]
    out["high_20d"] = max(lookback_highs) if lookback_highs else None
    out["low_20d"] = min(lookback_lows) if lookback_lows else None
    if len(closes) >= 6 and closes[-6]:
        out["change_5d_pct"] = (closes[-1] - closes[-6]) / closes[-6]
    if len(closes) >= LARGE_CAP_DAILY_BARS_LOOKBACK + 1:
        base = closes[-(LARGE_CAP_DAILY_BARS_LOOKBACK + 1)]
        if base:
            out["change_20d_pct"] = (closes[-1] - base) / base
    out["atr14"] = _atr(bars, period=LARGE_CAP_ATR_PERIOD)
    if len(bars) < LARGE_CAP_DAILY_BARS_LOOKBACK + 1:
        # Partial history -- still schedule a fill for the missing days.
        schedule_daily_fill(symbol)
    return out


def daily_bar_metrics(symbol: str) -> dict[str, Any]:
    """ATR(14), 5d/20d % change, 20d high/low. TTL-cached (see module docstring)."""
    now = time.monotonic()
    cached_ts = _daily_metrics_cache_ts.get(symbol, 0.0)
    if symbol in _daily_metrics_cache and (now - cached_ts) < LARGE_CAP_DAILY_METRICS_TTL_SEC:
        return _daily_metrics_cache[symbol]
    out = _compute_daily_bar_metrics(symbol)
    _daily_metrics_cache[symbol] = out
    _daily_metrics_cache_ts[symbol] = now
    return out


def range_expansion(
    price: float | None, prev_close: float | None, atr14: float | None,
) -> float | None:
    """Today's move relative to its own ATR -- a 1% day on a quiet stock beats
    a 3% day on a wild one (user-specified signal, ADR 014)."""
    if price is None or prev_close is None or not atr14:
        return None
    return abs(price - prev_close) / atr14


def build_row_metrics(
    symbol: str, *, price: float | None, prev_close: float | None, volume: float | None,
) -> dict[str, Any]:
    """Compose every swing metric for one row. Never blocks (see module docstring)."""
    from fundamentals import _fundamentals_cache

    fund = _fundamentals_cache.get(symbol, {})
    daily = daily_bar_metrics(symbol)
    return {
        "rvol": compute_rvol(volume, fund.get("average_volume")),
        "days_to_earnings": days_to_earnings(fund.get("earnings_date")),
        "atr_expansion": range_expansion(price, prev_close, daily.get("atr14")),
        "market_cap": fund.get("market_cap"),
        "float": fund.get("float_shares"),
        **daily,
    }


_SCORE_COMPONENTS = ("rvol", "atr_expansion", "change_20d_pct")


def _percentile_ranks(values: list[float | None]) -> list[float | None]:
    """Rank present values 0..1 (higher value -> higher rank); ``None`` stays ``None``."""
    present = [(i, v) for i, v in enumerate(values) if v is not None]
    ranks: list[float | None] = [None] * len(values)
    if not present:
        return ranks
    present.sort(key=lambda iv: iv[1])
    n = len(present)
    for rank, (i, _v) in enumerate(present):
        ranks[i] = rank / (n - 1) if n > 1 else 1.0
    return ranks


def compute_scores(rows: list[dict], *, weights: dict[str, float] | None = None) -> list[dict]:
    """Attach ``large_cap_score`` (0-100) + ``score_completeness`` to every row.

    Percentile ranks *within the current roster* (not raw values) so RVOL
    multiples and ATR multiples are never summed in mismatched units. Uses
    magnitude (``abs``) for every component -- the table is direction-
    agnostic; a strong down move should score as highly as a strong up move.
    """
    from constants import LARGE_CAP_SCORE_WEIGHTS

    weights = weights or LARGE_CAP_SCORE_WEIGHTS
    component_ranks = {
        c: _percentile_ranks(
            [abs(r[c]) if r.get(c) is not None else None for r in rows]
        )
        for c in _SCORE_COMPONENTS
    }
    out: list[dict] = []
    for idx, row in enumerate(rows):
        weighted_sum = 0.0
        weight_total = 0.0
        present = 0
        for c in _SCORE_COMPONENTS:
            rank = component_ranks[c][idx]
            weight = weights.get(c, 0.0)
            if rank is not None:
                weighted_sum += rank * weight
                weight_total += weight
                present += 1
        score = round(100 * weighted_sum / weight_total, 1) if weight_total > 0 else None
        out.append({
            **row,
            "large_cap_score": score,
            "score_completeness": round(present / len(_SCORE_COMPONENTS), 2),
        })
    return out


def reset_for_testing() -> None:
    _daily_metrics_cache.clear()
    _daily_metrics_cache_ts.clear()
