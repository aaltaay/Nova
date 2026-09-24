"""Chart bars from a loaded capture (split from ``sim.capture_player``).

Daily SSOT is IBKR (see chart_bars.py); 1d here is unused for the desk. A bar's
timestamp is its OPEN and its final OHLCV is not known until it closes; the
partial candle is built only from prints at or before the playhead. Candles
take only prints that set a price (``sale_conditions.py``); Time & Sales
replays them all.

Every candle is built from the recording's prints, never from the bar buckets
the recorder stored beside them (#535, operator decision 2026-09-23).
Recordings made before candles took only price-setting prints stored buckets
built from every print, so drawing them showed wicks no trade made (GRML
2026-09-22: 82 of 480 one-minute candles, a low of 13.19 where the trades
bottomed at 15.43) -- and after #511 a practice order would not fill there.
One path for every recording keeps the chart and the fills on the same prints.
"""
from __future__ import annotations

import bisect
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from capture.constants_capture import CAPTURE_CHART_DEFAULT_LIMIT, CAPTURE_CHART_MAX_LIMIT
from sale_conditions import row_sets_price

ET = ZoneInfo("America/New_York")


def _ts(row: dict[str, Any]) -> float:
    v = row.get("ts")
    return float(v) if isinstance(v, (int, float)) else 0.0


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


def _price_prints(state) -> list[dict[str, Any]]:
    """The recording's prints that set a price, filtered once (GRML 2026-09-22: 0.5 s over 790k prints)."""
    if state.price_prints is None:
        state.price_prints = [r for r in state.prints if row_sets_price(r)]
    return state.price_prints


def chart_bars(timeframe: str, limit: int, *, asof: float | None = None) -> list[dict[str, Any]]:
    """Intraday bars from capture's price-setting prints. Daily SSOT is IBKR (see chart_bars.py)."""
    from sim import capture_player as player

    state = player.snapshot()
    if state is None:
        return []
    from sim.chart_replay import INTERVAL_SECONDS, aggregate_prints, print_candle

    seconds = INTERVAL_SECONDS.get(timeframe)
    if seconds is None:
        return []
    if timeframe not in state.print_bar_cache:
        aggregated = aggregate_prints(_price_prints(state), seconds)
        state.print_bar_cache[timeframe] = (aggregated, [player._ts(r) for r in aggregated])
    rows, keys = state.print_bar_cache[timeframe]
    asof = player.asof_unix() if asof is None else asof
    bucket = int(asof // seconds) * seconds
    # A bar's timestamp is its OPEN. Its final OHLCV is not known until close.
    i = player._asof_index(keys, bucket - seconds)
    cap = max(1, min(int(limit or CAPTURE_CHART_DEFAULT_LIMIT), CAPTURE_CHART_MAX_LIMIT))
    bars = [_to_chart_bar(row) for row in rows[max(0, i - cap + 1):i + 1]]
    lo = bisect.bisect_left(state.print_keys, bucket)
    hi = bisect.bisect_right(state.print_keys, asof)
    partial = print_candle([r for r in state.prints[lo:hi] if row_sets_price(r)], bucket)
    if partial:
        bars.append(partial)
    return bars[-cap:]
