"""Causal signal bar construction, split-adjusted warmup, and Bollinger Bands calculation.

Standard deviation convention: population standard deviation (ddof=0) over the last N
completed signal candle closes, matching MetaTrader 5 iBands and standard Bollinger Bands.
Zero-volume / missing minutes are never forward-filled into fictitious tradable candles.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time as dtime

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SignalBar:
    """One completed signal-timeframe candle built strictly from observed 1m bars."""

    bar_index: int          # 0-based sequential index among observed signal bars for this stock
    session_date: str       # YYYY-MM-DD
    open_min: int           # minutes after midnight ET of bucket start (e.g. 570 = 09:30)
    close_min: int          # minutes after midnight ET when bucket completed (e.g. 575 = 09:35)
    open: float
    high: float
    low: float
    close: float
    volume: float
    middle: float | None = None
    upper: float | None = None
    lower: float | None = None
    std: float | None = None
    qualifies_long: bool = False


def timeframe_minutes(tf: str) -> int:
    if tf == "1m":
        return 1
    if tf == "5m":
        return 5
    if tf == "1h":
        return 60
    raise ValueError(f"Unsupported signal timeframe: {tf!r}")


def minute_of_day(t_val: dtime | str) -> int:
    if isinstance(t_val, dtime):
        return t_val.hour * 60 + t_val.minute
    parts = str(t_val).split(":")
    return int(parts[0]) * 60 + int(parts[1])


def format_hhmm(min_of_day: int) -> str:
    return f"{min_of_day // 60:02d}:{min_of_day % 60:02d}"


def bucket_close_minute(open_min: int, tf_min: int, regular_only: bool = False) -> int:
    """Clock-aligned bucket completion minute in America/New_York.

    For 1m: bar at 09:30 (open_min=570) completes at 09:31 (close_min=571).
    For 5m: bars in [09:30, 09:34] complete at 09:35 (close_min=575).
    For 1h in regular session (09:30-16:00): aligned to 09:30 open -> [09:30, 10:30), ..., [15:30, 16:00).
    For 1h in extended hours (04:00-16:00): aligned to hour boundaries -> [04:00, 05:00), ..., [15:00, 16:00).
    """
    if tf_min == 1:
        return open_min + 1
    if tf_min == 5:
        return (open_min // 5) * 5 + 5
    if tf_min == 60:
        if regular_only and open_min >= 570:
            offset = (open_min - 570) // 60
            return min(570 + (offset + 1) * 60, 960)
        return (open_min // 60) * 60 + 60
    raise ValueError(f"Unsupported tf_min={tf_min}")


def bucket_open_minute(open_min: int, tf_min: int, regular_only: bool = False) -> int:
    if tf_min == 1:
        return open_min
    if tf_min == 5:
        return (open_min // 5) * 5
    if tf_min == 60:
        if regular_only and open_min >= 570:
            return 570 + ((open_min - 570) // 60) * 60
        return (open_min // 60) * 60
    raise ValueError(f"Unsupported tf_min={tf_min}")


def causal_split_factor(
    splits_for_ticker: list[tuple[date, float, float]],
    bar_date: date,
    as_of_date: date,
) -> float:
    """Price factor to express a bar from `bar_date` in `as_of_date`'s raw price terms.

    Uses ONLY splits with `bar_date < execution_date <= as_of_date` (no future splits after `as_of_date`).
    For a 1-for-10 reverse split (split_from=10, split_to=1) executing on `as_of_date`, earlier prices
    multiply by 10.0 and earlier volumes divide by 10.0 so warmup bars match `as_of_date`'s raw prices.
    """
    if bar_date >= as_of_date or not splits_for_ticker:
        return 1.0
    factor = 1.0
    for exec_d, split_from, split_to in splits_for_ticker:
        if bar_date < exec_d <= as_of_date and split_from > 0 and split_to > 0:
            factor *= split_from / split_to
    return factor


def compute_bollinger_arrays(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    period: int,
    deviation: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compute SMA(period), population StdDev(period, ddof=0), Upper, Lower, and long rejection signal.

    Returns (middle, upper, lower, std, qualifies_long) of same length as `closes`.
    Indices `< period - 1` have NaN bands and `qualifies_long = False`.
    """
    n = len(closes)
    middle = np.full(n, np.nan, dtype=np.float64)
    std = np.full(n, np.nan, dtype=np.float64)
    upper = np.full(n, np.nan, dtype=np.float64)
    lower = np.full(n, np.nan, dtype=np.float64)
    qualifies = np.zeros(n, dtype=bool)
    if n < period or period < 1:
        return middle, upper, lower, std, qualifies

    c = np.asarray(closes, dtype=np.float64)
    lo = np.asarray(lows, dtype=np.float64)
    # Use cumulative sums of c and c^2 shifted by mean to preserve numerical precision
    c_mean = float(np.mean(c))
    dc = c - c_mean
    csum1 = np.empty(n + 1, dtype=np.float64)
    csum2 = np.empty(n + 1, dtype=np.float64)
    csum1[0] = 0.0
    csum2[0] = 0.0
    np.cumsum(dc, out=csum1[1:])
    np.cumsum(dc * dc, out=csum2[1:])

    w_sum1 = csum1[period:] - csum1[:-period]
    w_sum2 = csum2[period:] - csum2[:-period]
    w_mean_dc = w_sum1 / period
    w_var = np.maximum(0.0, (w_sum2 / period) - (w_mean_dc * w_mean_dc))
    w_std = np.sqrt(w_var)
    w_mid = w_mean_dc + c_mean
    w_up = w_mid + deviation * w_std
    w_lo = w_mid - deviation * w_std

    middle[period - 1:] = w_mid
    std[period - 1:] = w_std
    upper[period - 1:] = w_up
    lower[period - 1:] = w_lo

    # Exact signal rule (Section 4): Low[t] <= Lower[t] AND Close[t] > Lower[t]
    valid = ~np.isnan(lower)
    qualifies[valid] = (lo[valid] <= lower[valid]) & (c[valid] > lower[valid])
    return middle, upper, lower, std, qualifies


def build_signal_bars_from_1m(
    df_1m: pd.DataFrame,
    tf: str,
    period: int,
    deviation: float,
    *,
    regular_only: bool = False,
) -> list[SignalBar]:
    """Aggregate observed 1m bars into completed signal candles and compute Bollinger Bands.

    `df_1m` must have columns `['d', 'open_min', 'open', 'high', 'low', 'close', 'volume']` sorted by
    `(d, open_min)`, with prior sessions already split-adjusted to the evaluation date's basis.
    Zero-volume bars are dropped (no forward-filling).
    """
    if df_1m.empty:
        return []
    work = df_1m[df_1m["volume"] > 0].copy()
    if regular_only:
        work = work[(work["open_min"] >= 570) & (work["open_min"] < 960)]
    if work.empty:
        return []

    tf_min = timeframe_minutes(tf)
    if tf_min == 1:
        d_arr = work["d"].astype(str).to_numpy()
        omin = work["open_min"].to_numpy(dtype=np.int64)
        cmin = omin + 1
        o_arr = work["open"].to_numpy(dtype=np.float64)
        h_arr = work["high"].to_numpy(dtype=np.float64)
        l_arr = work["low"].to_numpy(dtype=np.float64)
        c_arr = work["close"].to_numpy(dtype=np.float64)
        v_arr = work["volume"].to_numpy(dtype=np.float64)
    else:
        omin_raw = work["open_min"].to_numpy(dtype=np.int64)
        b_open = np.array([bucket_open_minute(int(m), tf_min, regular_only) for m in omin_raw], dtype=np.int64)
        b_close = np.array([bucket_close_minute(int(m), tf_min, regular_only) for m in omin_raw], dtype=np.int64)
        work["b_open"] = b_open
        work["b_close"] = b_close
        grouped = work.groupby(["d", "b_open", "b_close"], sort=False, as_index=False).agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        d_arr = grouped["d"].astype(str).to_numpy()
        omin = grouped["b_open"].to_numpy(dtype=np.int64)
        cmin = grouped["b_close"].to_numpy(dtype=np.float64).astype(np.int64)
        o_arr = grouped["open"].to_numpy(dtype=np.float64)
        h_arr = grouped["high"].to_numpy(dtype=np.float64)
        l_arr = grouped["low"].to_numpy(dtype=np.float64)
        c_arr = grouped["close"].to_numpy(dtype=np.float64)
        v_arr = grouped["volume"].to_numpy(dtype=np.float64)

    mid, up, lo, sd, qual = compute_bollinger_arrays(c_arr, h_arr, l_arr, period, deviation)
    out: list[SignalBar] = []
    for i in range(len(c_arr)):
        is_valid = not np.isnan(mid[i])
        out.append(
            SignalBar(
                bar_index=i,
                session_date=str(d_arr[i]),
                open_min=int(omin[i]),
                close_min=int(cmin[i]),
                open=float(o_arr[i]),
                high=float(h_arr[i]),
                low=float(l_arr[i]),
                close=float(c_arr[i]),
                volume=float(v_arr[i]),
                middle=float(mid[i]) if is_valid else None,
                upper=float(up[i]) if is_valid else None,
                lower=float(lo[i]) if is_valid else None,
                std=float(sd[i]) if is_valid else None,
                qualifies_long=bool(qual[i]),
            )
        )
    return out
