"""Chart knowledge boundary for SIM; never expose final, unfinished OHLCV."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
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
    from sim import history_playback
    historical = history_playback.bars(symbol, timeframe, limit, now)
    if historical is not None:
        return response(symbol, timeframe, historical, now, source="ibkr",
                        replay_mode=history_playback.snapshot(symbol)["source"])
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
    session_start = None
    if timeframe in INTERVAL_SECONDS:
        session_start = datetime.combine(
            now.astimezone(ET).date(), datetime.min.time(), ET,
        ).timestamp()
    stored = read(symbol, timeframe, limit,
                  through_ts=completed_start_cutoff(timeframe, now),
                  from_ts=session_start)
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


CENT = Decimal("0.01")


def _cent(value: float, rounding: str) -> float:
    return float(Decimal(repr(float(value))).quantize(CENT, rounding=rounding))


def penny_bar(bar: dict) -> dict:
    """IBKR's own presentation of a print-built bar (D-056).

    IB publishes TRADES bars on the cent while the tick stream carries
    sub-penny prints, so raw aggregation of the same minute reads as a
    mismatch against ``reqHistoricalData``. Rounding open/close half-up, high
    up and low down reproduces IB's bars exactly over the SPY reconciliation.
    """
    return dict(
        bar,
        open=_cent(bar["open"], ROUND_HALF_UP),
        high=_cent(bar["high"], ROUND_CEILING),
        low=_cent(bar["low"], ROUND_FLOOR),
        close=_cent(bar["close"], ROUND_HALF_UP),
    )


def _flat(ts: int, close: float) -> dict:
    return dict(ts=ts, open=close, high=close, low=close, close=close, volume=0.0)


def fill_flat_buckets(buckets: list[dict], seconds: int) -> list[dict]:
    """Zero-volume bars at the prior close for intervals with no reported print.

    IB emits these; print aggregation cannot, because a silent minute has no
    row to aggregate. Only gaps *between* reported buckets are filled -- never
    before the first print, which would invent a session that had not started.
    """
    ordered = sorted(buckets, key=lambda bar: bar["ts"])
    if len(ordered) < 2:
        return ordered
    out = [ordered[0]]
    for bar in ordered[1:]:
        previous = out[-1]
        for ts in range(previous["ts"] + seconds, bar["ts"], seconds):
            out.append(_flat(ts, previous["close"]))
        out.append(bar)
    return out


def extend_flat_tail(buckets: list[dict], seconds: int, through: float) -> list[dict]:
    """Carry a silent tail forward to the last interval that closed by ``through``.

    Without this the pane stops at the last print while Time & Sales runs on,
    so a quiet stretch reads as a stalled chart rather than a quiet market.
    """
    if not buckets:
        return buckets
    out, last = list(buckets), buckets[-1]
    ts = last["ts"] + seconds
    while ts + seconds <= through:
        out.append(_flat(ts, last["close"]))
        ts += seconds
    return out


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
