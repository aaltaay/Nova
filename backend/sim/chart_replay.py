"""Chart knowledge boundary for SIM; never expose final, unfinished OHLCV."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from constants_sim import SIM_SYMBOL
from ibkr.historical_derive import unix_to_iso

ET = ZoneInfo("America/New_York")
INTERVAL_SECONDS = {
    "10Sec": 10, "1Min": 60, "5Min": 300, "15Min": 900,
    "30Min": 1800, "1Hour": 3600,
}
CALENDAR_TIMEFRAMES = frozenset({"1Day", "1Week", "1Month"})


def completed_start_cutoff(timeframe: str, now: datetime) -> float:
    """Latest admissible start; calendar bars carry UTC session-date labels."""
    seconds = INTERVAL_SECONDS.get(timeframe)
    if seconds:
        return now.timestamp() - seconds
    day = now.astimezone(ET).date()
    if timeframe == "1Week":
        day -= timedelta(days=day.weekday())
    elif timeframe == "1Month":
        day = day.replace(day=1)
    elif timeframe != "1Day":
        raise ValueError(f"Unsupported replay timeframe: {timeframe}")
    return datetime.combine(day, datetime.min.time(), timezone.utc).timestamp() - 1


def response(symbol: str, timeframe: str, bars: list[dict], now: datetime,
             *, source: str, replay_mode: str) -> dict:
    return {
        "symbol": symbol, "timeframe": timeframe, "bars": bars, "source": source,
        "coverage": {
            "as_of": now.astimezone(timezone.utc).isoformat(),
            # The final row may be partial; don't claim it is complete.
            "complete_through": next((b["t"] for b in reversed(bars)
                                      if not b.get("partial")), None),
            "filling": False, "replay": True, "replay_mode": replay_mode,
        },
    }


def fetch_replay_bars(symbol: str, timeframe: str, limit: int) -> dict:
    from bars_store import read
    from sim import capture_player, market, replay, session_clock

    now = session_clock.now_et()
    selected = (replay.status_payload() or {}).get("replay_symbol")
    captured = replay.is_capture_replay() and symbol == selected
    if captured and timeframe in INTERVAL_SECONDS:
        bars = capture_player.chart_bars(timeframe, limit, asof=now.timestamp())
        mode = "trades" if capture_player.has_prints() else "completed_bars"
        return response(symbol, timeframe, bars, now, source="capture", replay_mode=mode)
    if symbol == SIM_SYMBOL:
        # A capture has no synthetic calendar history. Missing is genuinely empty.
        bars = [] if captured else market.chart_bars(symbol, timeframe, limit)["bars"]
        return response(symbol, timeframe, bars, now, source="sim",
                        replay_mode="completed_bars" if captured else "synthetic")
    stored = read(symbol, timeframe, limit,
                  through_ts=completed_start_cutoff(timeframe, now))
    return response(symbol, timeframe, (stored or {}).get("bars", []), now,
                    source="ibkr", replay_mode="completed_bars")


def print_candle(prints: list[dict], bucket: float) -> dict | None:
    """Aggregate reached prints only; input has already been time-windowed."""
    rows = [p for p in prints if float(p.get("price") or 0) > 0]
    if not rows:
        return None
    prices = [float(p["price"]) for p in rows]
    return {
        "t": unix_to_iso(bucket), "o": prices[0], "h": max(prices),
        "l": min(prices), "c": prices[-1],
        "v": sum(max(0, float(p.get("size") or 0)) for p in rows),
        "partial": True,
    }


def aggregate_prints(prints: list[dict], seconds: int) -> list[dict]:
    """Build cached full buckets; callers still gate them by interval end."""
    buckets: dict[int, dict] = {}
    for row in prints:
        price = float(row.get("price") or 0)
        if price <= 0:
            continue
        bucket = int(float(row["ts"]) // seconds) * seconds
        size = max(0, float(row.get("size") or 0))
        if bucket not in buckets:
            buckets[bucket] = dict(ts=bucket, open=price, high=price, low=price,
                                   close=price, volume=size)
        else:
            bar = buckets[bucket]
            bar["high"] = max(bar["high"], price)
            bar["low"] = min(bar["low"], price)
            bar["close"] = price
            bar["volume"] += size
    return list(buckets.values())
