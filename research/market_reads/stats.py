"""One stock-day's numbers, computed on demand from the front door's own reads (ADR 059).

Sources: the day's minute bars (``reads.bars``, Massive's minute file, 04:00-20:00 ET, no closing cross) for prices,
volume and trade counts; its NBBO quotes (``reads.quotes``) for the spread; the day files (``daily.sessions``) for the
previous close, the official day bar and daily relative volume. Every price is raw, as traded: never split-adjusted
(compare across a split only through ``splits``). Percents are percent points (1.5 = +1.5%); times are ET ``HH:MM``,
the start of the minute bar. The answer describes the finished day: its whole-day fields read the future relative to
any moment inside it; the relative volume at a minute uses only bars that started before that minute.

Windows (minute bars by start time) are ``research/orb``'s, so the numbers match ``orb.duckdb``: premarket is
``build_premarket``'s (bars before 09:30; its last close, its high and the high's minute), the first 30 minutes are
its ``h30 / l30 / v30 / c30`` (09:30-10:00), the first 5 minutes and the regular session are ``build_store``'s
``o5_*`` (09:30-09:35) and ``rth_*`` (09:30-16:00; the open is the first bar's open, the close the 15:59 bar's, not
the official close -- ``day_bar`` has that). Two differences, on purpose: a high's (low's) time is the first minute
that reached it (DuckDB's ``arg_max`` picks any minute on a tie), and ``rvol.open5`` is ``build_store``'s opening
rvol (09:30-09:35 volume over the prior sessions' average) over ``rvol_days`` sessions instead of 14.

Speed, measured 2026-10-18 (indexed files): the minute read 0.2 s; 20 prior minute reads 2.3 s (``rvol_days`` is
capped at ``MAX_RVOL_DAYS``); a whole day's quotes 2.3 s (IRD 2026-09-09, 407k) and 2.6 s (GME 2021-01-27, 499k).
A quote read costs the ticker's whole day whatever the window, so the spread is measured over the whole regular
session and over its first 30 minutes from one read. A day whose files are not indexed yet reads much slower.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from market_reads import daily, reads, slots

PREMARKET, OPEN, OPEN5, OPEN30, CLOSE = 4 * 60, 9 * 60 + 30, 9 * 60 + 35, 10 * 60, 16 * 60
CHECKPOINTS = ("09:35", "09:45", "10:00", "10:30", "11:00", "12:00", "16:00")
MAX_RVOL_DAYS = 60           # 60 prior minute reads ~7 s at the measured 0.11 s each
RULES = {
    "windows": "minute bars by start time: premarket 04:00-09:30, first_5min 09:30-09:35, first_30min 09:30-10:00, "
               "regular 09:30-16:00, whole_day 04:00-20:00 (research/orb's windows)",
    "open_close": "a window's open is its first bar's open, its close its last bar's close (minute bars carry no "
                  "closing cross: day_bar has the official open / high / low / close)",
    "change_pct": "a window's close vs prev_close; high_pct its high vs prev_close; range_pct (high - low) / open",
    "times": "ET HH:MM, the start of the first minute bar that reached the high (low)",
    "prev_close": "the close of the symbol's previous session in the day files (raw)",
    "vwap": "approximate, minute typical price: sum((high + low + close) / 3 x volume) / sum(volume); the minute "
            "files carry no vwap column",
    "trades": "count is the sum of the minute bars' transactions; avg_size is volume / count",
    "spread": "time-weighted median NBBO spread: each quote lasts until the next change; a quote with a zero or "
              "missing side, or crossed (ask < bid), is left out (locked, ask == bid, counts as 0); bps of the "
              "midpoint; the quote in force at 09:30 is the last one before it",
    "rvol_by_minute": "cumulative volume from 04:00 (premarket included) of bars starting before the minute, over "
                      "the mean of the same on the prior rvol_days sessions the symbol traded",
    "rvol_open5": "research/orb build_store's opening rvol: 09:30-09:35 volume over the prior sessions' mean",
    "rvol_daily": "the day bar's volume over the mean day-bar volume of the prior rvol_days sessions",
    "raw": "every price raw, as traded: never split-adjusted",
}
UNITS = {"prices": "dollars, raw", "volume": "shares (minute bars: Massive's own minute rule, no closing cross at "
         "16:00; day bar: whole session with odd lots, the consolidated tape's from 2024-02-21)", "pct": "percent points (1.5 = +1.5%)", "spread": "cents and basis points of the midpoint",
         "times": "ET HH:MM, minute-bar start"}


def _f(value) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def _pct(a, b) -> float | None:
    a, b = _f(a), _f(b)
    return None if a is None or not b else (a / b - 1.0) * 100.0


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _minute(hhmm: str) -> int:
    hh, mm = hhmm.split(":")
    return int(hh) * 60 + int(mm)


def _minutes(frame: pd.DataFrame) -> pd.DataFrame:
    """A minute read with its ET minute of day (``m``); an empty read keeps the columns used below."""
    if not len(frame):
        return pd.DataFrame(columns=["m", "open", "high", "low", "close", "volume", "transactions"])
    out = frame.copy()
    out["m"] = out["time_et"].dt.hour * 60 + out["time_et"].dt.minute
    return out.sort_values("m").reset_index(drop=True)


def _window(bars: pd.DataFrame, lo: int, hi: int, prev_close: float | None) -> dict | None:
    """OHLCV of the bars starting in ``[lo, hi)``, the minutes of the high and low, and the moves vs prev_close."""
    part = bars[(bars["m"] >= lo) & (bars["m"] < hi)]
    if not len(part):
        return None
    high, low = part["high"].max(), part["low"].min()
    first_open, last_close = _f(part["open"].iloc[0]), _f(part["close"].iloc[-1])
    volume = float(part["volume"].sum())
    trades = int(part["transactions"].fillna(0).sum())
    return {"open": first_open, "high": _f(high), "low": _f(low), "close": last_close, "volume": volume,
            "bars": len(part), "transactions": trades,
            "high_time": _hhmm(int(part.loc[part["high"] == high, "m"].iloc[0])),
            "low_time": _hhmm(int(part.loc[part["low"] == low, "m"].iloc[0])),
            "range_pct": (float(high) - float(low)) / first_open * 100.0 if first_open else None,
            "change_pct": _pct(last_close, prev_close), "high_pct": _pct(high, prev_close)}


def _vwap(bars: pd.DataFrame, lo: int, hi: int) -> float | None:
    part = bars[(bars["m"] >= lo) & (bars["m"] < hi)]
    volume = part["volume"].sum()
    if not len(part) or not volume:
        return None
    typical = (part["high"] + part["low"] + part["close"]) / 3.0
    return float((typical * part["volume"]).sum() / volume)


def _trades(window: dict | None) -> dict | None:
    if not window:
        return None
    count = window["transactions"]
    return {"count": count, "avg_size": window["volume"] / count if count else None}


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float | None:
    keep = weights > 0
    if not keep.any():
        return None
    values, weights = values[keep], weights[keep]
    order = np.argsort(values, kind="stable")
    cum = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(cum, cum[-1] / 2.0)])


def spread_stats(quotes: pd.DataFrame, day: str, start: str, end: str) -> dict | None:
    """The time-weighted median NBBO spread over ``[start, end)`` ET (``RULES['spread']``): ``median_cents``,
    ``median_bps``, ``quotes`` (changes inside the window), ``valid_share`` (share of the window with a usable quote).
    ``None`` with no quote in force during the window."""
    if not len(quotes):
        return None
    lo, hi = reads._ns(day, start), reads._ns(day, end)
    q = quotes.sort_values("sip_timestamp", kind="stable")
    ts = q["sip_timestamp"].to_numpy(dtype="int64")
    ends = np.append(ts[1:], hi)
    durations = (np.minimum(ends, hi) - np.maximum(ts, lo)).clip(min=0).astype("float64")
    bid = q["bid_price"].to_numpy(dtype="float64")
    ask = q["ask_price"].to_numpy(dtype="float64")
    usable = (bid > 0) & (ask > 0) & (ask >= bid) & np.isfinite(bid) & np.isfinite(ask)
    weights = np.where(usable, durations, 0.0)
    if not weights.sum():
        return None
    width = ask - bid
    mid = (ask + bid) / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        bps = np.where(usable, width / mid * 1e4, 0.0)
    cents, basis = _weighted_median(width * 100.0, weights), _weighted_median(bps, weights)
    return {"window": f"{start}-{end}", "median_cents": None if cents is None else round(cents, 4),
            "median_bps": None if basis is None else round(basis, 2), "quotes": int(((ts >= lo) & (ts < hi)).sum()),
            "valid_share": float(weights.sum() / (hi - lo))}


def _cumulative(bars: pd.DataFrame, minute: int) -> float:
    return float(bars.loc[bars["m"] < minute, "volume"].sum())


def _rvol(today: pd.DataFrame, prior: list[pd.DataFrame], day_volume: float | None,
          prior_day_volumes: list[float]) -> dict:
    by_minute = {}
    for hhmm in CHECKPOINTS:
        m = _minute(hhmm)
        mine = _cumulative(today, m)
        base = [_cumulative(p, m) for p in prior]
        avg = sum(base) / len(base) if base else None
        by_minute[hhmm] = {"cum_volume": mine, "avg_cum_volume": avg, "rvol": mine / avg if avg else None}
    open5 = float(today.loc[(today["m"] >= OPEN) & (today["m"] < OPEN5), "volume"].sum())
    base5 = [float(p.loc[(p["m"] >= OPEN) & (p["m"] < OPEN5), "volume"].sum()) for p in prior]
    avg5 = sum(base5) / len(base5) if base5 else None
    avg_day = sum(prior_day_volumes) / len(prior_day_volumes) if prior_day_volumes else None
    return {"by_minute": by_minute,
            "open5": {"volume": open5, "avg_volume": avg5, "rvol": open5 / avg5 if avg5 else None},
            "daily": {"volume": day_volume, "avg_volume": avg_day,
                      "rvol": day_volume / avg_day if avg_day and day_volume is not None else None}}


def stock_day_stats(symbol: str, day: str, rvol_days: int = 20, spread: bool = True) -> dict:
    """``symbol`` on ``day``: what the session did, from minute bars, quotes and the day files (``RULES``, ``UNITS``).

    Keys: ``symbol, day, prev_close, prev_close_day``; ``day_bar`` (the day file's official ``open, high, low, close``,
    whole-session ``volume``, ``transactions``, ``change_pct``, ``gap_pct``); ``premarket``, ``first_5min``,
    ``first_30min``, ``regular`` and ``whole_day`` windows (``open, high, low, close, volume, bars, transactions,
    high_time, low_time, range_pct, change_pct, high_pct``; ``None`` with no bar in the window); ``vwap``
    (``regular``, ``whole_day``, ``method``); ``trades`` (``regular`` / ``whole_day``: ``count``, ``avg_size``);
    ``spread`` (``regular``, ``first_30min``: ``median_cents, median_bps, quotes, valid_share``; ``None`` when
    ``spread`` is False); ``rvol`` (``basis_sessions``, ``by_minute`` at each of ``CHECKPOINTS`` with ``cum_volume,
    avg_cum_volume, rvol``; ``open5``; ``daily``); ``rules``, ``units``, ``seconds`` (each read's time).

    ``rvol_days`` (1..``MAX_RVOL_DAYS``) prior sessions the symbol traded, from the day files; fewer when it had
    fewer (``rvol.basis_sessions`` says how many). Raises ``LookupError`` when the day has no day file or the symbol
    did not trade it."""
    symbol = str(symbol or "").strip().upper()
    rvol_days = int(rvol_days)
    if not 1 <= rvol_days <= MAX_RVOL_DAYS:
        raise ValueError(f"rvol_days must be 1..{MAX_RVOL_DAYS} (each is a minute-file read), not {rvol_days}")
    target = date.fromisoformat(day)
    first = (target - timedelta(days=rvol_days * 2 + daily.PREV_LOOKBACK_DAYS)).isoformat()
    seconds: dict[str, float] = {}
    t0 = pd.Timestamp.now()

    def lap(name: str, since: pd.Timestamp) -> pd.Timestamp:
        now = pd.Timestamp.now()
        seconds[name] = round((now - since).total_seconds(), 2)
        return now

    with slots.heavy(f"stock_day_stats {symbol} {day}"):
        days = daily.sessions(symbol, first, day)
        t = lap("day_files", t0)
        if not len(days) or days["date"].iloc[-1] != day:
            raise LookupError(f"{symbol} has no {daily.SIM_MASSIVE_DAYS} row on {day}: not a session on disk, or "
                              "the symbol did not trade it")
        today = _minutes(reads.bars(symbol, day, "1m"))
        t = lap("minutes", t)
        prior_days = list(days["date"].iloc[:-1].tail(rvol_days))
        prior = [_minutes(reads.bars(symbol, d, "1m")) for d in prior_days]
        t = lap("prior_minutes", t)
        quotes = reads.quotes(symbol, day, None, "16:00") if spread else None
        lap("quotes", t)
    row = days.iloc[-1]
    prev_close = _f(row["prev_close"])
    prev_day = days["date"].iloc[-2] if len(days) > 1 else days.attrs.get("prev_close_from")
    regular = _window(today, OPEN, CLOSE, prev_close)
    whole = _window(today, PREMARKET, 24 * 60, prev_close)
    answer = {
        "symbol": symbol, "day": day, "prev_close": prev_close, "prev_close_day": prev_day,
        "day_bar": {"open": _f(row["open"]), "high": _f(row["high"]), "low": _f(row["low"]),
                    "close": _f(row["close"]), "volume": _f(row["volume"]),
                    "transactions": None if pd.isna(row["transactions"]) else int(row["transactions"]),
                    "change_pct": _pct(row["close"], prev_close), "gap_pct": _pct(row["open"], prev_close)},
        "premarket": _window(today, PREMARKET, OPEN, prev_close),
        "first_5min": _window(today, OPEN, OPEN5, prev_close),
        "first_30min": _window(today, OPEN, OPEN30, prev_close),
        "regular": regular, "whole_day": whole,
        "vwap": {"regular": _vwap(today, OPEN, CLOSE), "whole_day": _vwap(today, PREMARKET, 24 * 60),
                 "method": "approximate, minute typical price"},
        "trades": {"regular": _trades(regular), "whole_day": _trades(whole)},
        "spread": None if quotes is None else {
            "regular": spread_stats(quotes, day, "09:30", "16:00"),
            "first_30min": spread_stats(quotes, day, "09:30", "10:00")},
        "rvol": {"basis_sessions": len(prior_days), "basis_days": prior_days,
                 **_rvol(today, prior, _f(row["volume"]), [float(v) for v in days["volume"].iloc[:-1].tail(rvol_days)])},
        "rules": RULES, "units": UNITS,
    }
    seconds["total"] = round((pd.Timestamp.now() - t0).total_seconds(), 2)
    answer["seconds"] = seconds
    return answer
