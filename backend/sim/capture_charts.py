"""Chart bars from a loaded capture (split from ``sim.capture_player``).

Daily SSOT is IBKR (see chart_bars.py); 1d here is unused for the desk. A bar's
timestamp is its OPEN and its final OHLCV is not known until it closes; the
partial candle is built only from prints at or before the playhead.
"""
from __future__ import annotations

import bisect
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from capture.constants_capture import CAPTURE_CHART_DEFAULT_LIMIT, CAPTURE_CHART_MAX_LIMIT

ET = ZoneInfo("America/New_York")


def _ts(row: dict[str, Any]) -> float:
    v = row.get("ts")
    return float(v) if isinstance(v, (int, float)) else 0.0


def _bar_tf(timeframe: str) -> str:
    tf = (timeframe or "").strip().lower().replace(" ", "")
    if tf in ("10s", "10sec", "10"):
        return "10s"
    if tf in ("5m", "5min", "5minute"):
        return "5m"
    if tf in ("1d", "1day", "day", "daily"):
        return "1d"
    return "1m"


def _to_chart_bar(row: dict[str, Any]) -> dict[str, Any]:
    ts = _ts(row)
    t_iso = datetime.fromtimestamp(ts, tz=ET).astimezone(timezone.utc).isoformat()
    return {
        "t": t_iso,
        "o": float(row.get("open") or row.get("o") or 0),
        "h": float(row.get("high") or row.get("h") or 0),
        "l": float(row.get("low") or row.get("l") or 0),
        "c": float(row.get("close") or row.get("c") or 0),
        "v": float(row.get("volume") or row.get("v") or 0),
    }


def chart_bars(timeframe: str, limit: int, *, asof: float | None = None) -> list[dict[str, Any]]:
    """Intraday bars from capture. Daily SSOT is IBKR (see chart_bars.py); 1d here is unused for desk."""
    from sim import capture_player as player

    state = player.snapshot()
    if state is None:
        return []
    from sim.chart_replay import INTERVAL_SECONDS, aggregate_prints, print_candle
    from ibkr.historical_derive import derive_from_1min

    seconds = INTERVAL_SECONDS.get(timeframe)
    if seconds is None:
        return []
    kind = _bar_tf(timeframe)
    derive = timeframe in ("15Min", "30Min", "1Hour")
    if derive:
        kind = "1m"
    rows = state.bars.get(kind) or []
    keys = state.bar_keys.get(kind) or []
    if not rows and state.prints:
        if timeframe not in state.print_bar_cache:
            aggregated = aggregate_prints(state.prints, seconds)
            state.print_bar_cache[timeframe] = (aggregated, [player._ts(r) for r in aggregated])
        rows, keys = state.print_bar_cache[timeframe]
        derive = False
    asof = player.asof_unix() if asof is None else asof
    bucket = int(asof // seconds) * seconds
    # A bar's timestamp is its OPEN. Its final OHLCV is not known until close.
    i = player._asof_index(keys, bucket - (60 if derive else seconds))
    cap = max(1, min(int(limit or CAPTURE_CHART_DEFAULT_LIMIT), CAPTURE_CHART_MAX_LIMIT))
    source_cap = cap * (seconds // 60) if derive else cap
    bars = list({r["t"]: r for r in (
        _to_chart_bar(row) for row in rows[max(0, i - source_cap + 1):i + 1]
    )}.values())
    if derive:
        bars = derive_from_1min(bars, timeframe)
    lo = bisect.bisect_left(state.print_keys, bucket)
    hi = bisect.bisect_right(state.print_keys, asof)
    partial = print_candle(state.prints[lo:hi], bucket)
    if partial:
        bars.append(partial)
    return bars[-cap:]
