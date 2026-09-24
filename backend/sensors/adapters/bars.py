"""VWAP, MACD, and EMA adapters from stored / Sim 1Min bars.

The VWAP is the session's from 04:00 ET -- the chart's anchor -- on the newest stored session
(ADR 036: it used to average whatever the newest 240 bars were).
"""
from __future__ import annotations

from datetime import datetime, time as dtime
from typing import Any
from zoneinfo import ZoneInfo

from constants_sensors import (
    SENSOR_EMA_PERIODS,
    SENSOR_MACD_FAST,
    SENSOR_MACD_SIGNAL,
    SENSOR_MACD_SLOW,
    SENSOR_SESSION_BAR_LIMIT,
    SENSOR_SESSION_START_ET,
    SENSOR_TICK_DOLLARS,
    SENSOR_VWAP_SLOPE_LONG,
    SENSOR_VWAP_SLOPE_SHORT,
)
from sensors.envelope import build_envelope
from sensors.feeds import bars_as_of, get_bars
from sensors.math_indicators import last_ema, macd_from_closes, session_vwap, slope_last

ET = ZoneInfo("America/New_York")


def session_of(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The newest session's bars from 04:00 ET (the bars' own Eastern date)."""
    if not bars:
        return []
    day = datetime.fromtimestamp(float(bars[-1]["t"]), ET).date()
    hh, mm = (int(x) for x in SENSOR_SESSION_START_ET.split(":"))
    start = datetime.combine(day, dtime(hh, mm), ET).timestamp()
    return [b for b in bars if float(b["t"]) >= start]


def _need_bars(sensor: str, symbol: str, bars: list, source: str | None, need: int) -> dict[str, Any] | None:
    if len(bars) >= need:
        return None
    return build_envelope(
        sensor=sensor,
        symbol=symbol,
        status="live",
        data={"source": source, "bars": len(bars), "need": need},
        error=f"Need {need} 1Min bars; have {len(bars)}. Open a chart, or load a replay in Sim.",
    )


def read_vwap(symbol: str) -> dict[str, Any]:
    bars, source = get_bars(symbol, "1Min", SENSOR_SESSION_BAR_LIMIT)
    bars = session_of(bars)
    missing = _need_bars("vwap", symbol, bars, source, 2)
    if missing:
        return missing
    stats = session_vwap(bars)
    running = list(stats.pop("running") or [])
    dist = stats.get("distance")
    ticks = None
    if dist is not None:
        ticks = round(dist / SENSOR_TICK_DOLLARS, 4)
    return build_envelope(
        sensor="vwap",
        symbol=symbol,
        status="live",
        data={
            "source": source,
            "bars_as_of": bars_as_of(bars),
            **stats,
            "distance_ticks": ticks,
            "tick_dollars": SENSOR_TICK_DOLLARS,
            "slope_5": slope_last(running, SENSOR_VWAP_SLOPE_SHORT),
            "slope_15": slope_last(running, SENSOR_VWAP_SLOPE_LONG),
            "anchor": f"{SENSOR_SESSION_START_ET} ET",
            "note": "Session VWAP from 04:00 ET (the chart's): 1Min typical price * volume. Not ticker.vwap.",
        },
    )


def read_macd(symbol: str) -> dict[str, Any]:
    need = SENSOR_MACD_SLOW + SENSOR_MACD_SIGNAL
    bars, source = get_bars(symbol)
    missing = _need_bars("macd", symbol, bars, source, need)
    if missing:
        return missing
    closes = [float(b["c"]) for b in bars]
    calc = macd_from_closes(closes, SENSOR_MACD_FAST, SENSOR_MACD_SLOW, SENSOR_MACD_SIGNAL)
    return build_envelope(
        sensor="macd",
        symbol=symbol,
        status="live",
        data={
            "source": source,
            "bars_as_of": bars_as_of(bars),
            "fast": SENSOR_MACD_FAST,
            "slow": SENSOR_MACD_SLOW,
            "signal_period": SENSOR_MACD_SIGNAL,
            **calc,
        },
    )


def read_emas(symbol: str) -> dict[str, Any]:
    bars, source = get_bars(symbol)
    missing = _need_bars("emas", symbol, bars, source, 9)
    if missing:
        return missing
    emas = {f"ema_{period}": last_ema(bars, period) for period in SENSOR_EMA_PERIODS}
    last = float(bars[-1]["c"])
    return build_envelope(
        sensor="emas",
        symbol=symbol,
        status="live",
        data={
            "source": source,
            "bars_as_of": bars_as_of(bars),
            "last": last,
            **emas,
            "note": "1Min closes. EMA 200 stays ready=false until 200 bars exist.",
        },
    )
