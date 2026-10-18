"""Point-in-time Universe A (Liquid Reference) and Universe B (Morning Active Scanner) selection.

Implements Section 3 without hindsight:
- Universe A (`liquid_reference`): U.S. common stocks (`CS`, `ADRC`, including delisted common stocks),
  excluding ETFs/warrants/preferreds/OTC, prior regular close $5-$200, prior 20-day average daily dollar
  volume >= $20M, ranked deterministically by point-in-time ADV20 descending.
- Universe B (`morning_active`): Causal minute-by-minute scanner over U.S. common stocks trading between
  $1 and $30, current price >= 1.10 * prev_close, cumulative eligible dollar volume since 04:00 ET >= $500,000,
  ranked by cumulative dollar volume known at that minute descending, top 20 refreshed each completed minute.
  A stock dropping out of the top-20 scanner remains managed if already held in an open basket.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

LIQUID_PRICE_MIN = 5.0
LIQUID_PRICE_MAX = 200.0
LIQUID_ADV20_MIN = 20_000_000.0

ACTIVE_PRICE_MIN = 1.0
ACTIVE_PRICE_MAX = 30.0
ACTIVE_MIN_GAIN_RATIO = 1.10
ACTIVE_MIN_CUM_DOLLAR_VOL = 500_000.0
ACTIVE_TOP_N = 20


@dataclass(frozen=True)
class UniverseCandidate:
    ticker: str
    priority_metric: float      # ADV20 for Universe A; contemporaneous cum_dollar_vol for Universe B
    prev_close: float
    current_price: float


def is_eligible_common_stock(
    ticker: str,
    sec_type: str | None,
    primary_exchange: str | None,
) -> bool:
    """True for U.S.-listed common stocks / ADRs (including delisted 1-4 letter common tickers)."""
    if primary_exchange is not None and primary_exchange not in ("XNAS", "XNYS", "XASE", "ARCX", "BATS"):
        return False
    if sec_type in ("CS", "ADRC"):
        return True
    if sec_type is None:
        sym = str(ticker or "").strip()
        return 1 <= len(sym) <= 4 and sym.isalpha() and sym.isupper()
    return False


def rank_liquid_universe_at_minute(
    candidates: list[tuple[str, float, float, float]],
    *,
    price_min: float = LIQUID_PRICE_MIN,
    price_max: float = LIQUID_PRICE_MAX,
    adv20_min: float = LIQUID_ADV20_MIN,
) -> dict[str, UniverseCandidate]:
    """Filter and rank Universe A candidates at a given minute.

    `candidates`: list of `(ticker, prev_close, adv20_usd, current_price)`.
    Returns dict mapping `ticker -> UniverseCandidate` ordered by `(adv20_usd DESC, ticker ASC)`.
    """
    qualified: list[UniverseCandidate] = []
    for ticker, prev_close, adv20_usd, current_price in candidates:
        if prev_close < price_min or prev_close > price_max:
            continue
        if current_price < price_min or current_price > price_max:
            continue
        if adv20_usd < adv20_min:
            continue
        qualified.append(
            UniverseCandidate(
                ticker=ticker,
                priority_metric=float(adv20_usd),
                prev_close=float(prev_close),
                current_price=float(current_price),
            )
        )
    qualified.sort(key=lambda c: (-c.priority_metric, c.ticker))
    return {c.ticker: c for c in qualified}


def rank_morning_active_scanner_at_minute(
    candidates: list[tuple[str, float, float, float]],
    *,
    price_min: float = ACTIVE_PRICE_MIN,
    price_max: float = ACTIVE_PRICE_MAX,
    min_gain_ratio: float = ACTIVE_MIN_GAIN_RATIO,
    min_cum_dollar_vol: float = ACTIVE_MIN_CUM_DOLLAR_VOL,
    top_n: int = ACTIVE_TOP_N,
) -> dict[str, UniverseCandidate]:
    """Causal minute-by-minute Morning Active-Stock Scanner (Section 3.B).

    `candidates`: list of `(ticker, prev_close, cum_dollar_vol_since_0400, current_price)`
    computed strictly from bars completed at or before the current minute.
    Returns top `top_n` candidates ordered by `(cum_dollar_vol_since_0400 DESC, ticker ASC)`.
    """
    qualified: list[UniverseCandidate] = []
    for ticker, prev_close, cum_dvol, current_price in candidates:
        if prev_close <= 0 or current_price <= 0:
            continue
        if current_price < price_min or current_price > price_max:
            continue
        if current_price + 1e-9 < prev_close * min_gain_ratio:
            continue
        if cum_dvol + 1e-9 < min_cum_dollar_vol:
            continue
        qualified.append(
            UniverseCandidate(
                ticker=ticker,
                priority_metric=float(cum_dvol),
                prev_close=float(prev_close),
                current_price=float(current_price),
            )
        )
    qualified.sort(key=lambda c: (-c.priority_metric, c.ticker))
    picked = qualified[: max(0, int(top_n))]
    return {c.ticker: c for c in picked}


def compute_intraday_cumulative_dollar_volume(df_day_1m: pd.DataFrame) -> np.ndarray:
    """Compute cumulative dollar volume (`sum(close * volume)`) since 04:00 ET for each 1m bar."""
    if df_day_1m.empty:
        return np.zeros(0, dtype=np.float64)
    dvol = df_day_1m["close"].to_numpy(dtype=np.float64) * df_day_1m["volume"].to_numpy(dtype=np.float64)
    return np.cumsum(dvol)
