"""Immutable historical selection; candles and tape share one event-time cut."""
from __future__ import annotations

import bisect
import threading
from functools import wraps
from datetime import date, datetime, time, timedelta, timezone

from constants_sim import SIM_HISTORY_TAPE_ROWS
from sim import history_store as store
from sim.history_store import ET

_lock = threading.RLock()


def synchronized(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with _lock:
            return fn(*args, **kwargs)
    return wrapped


_selection: dict | None = None
# Every downloaded print (Time & Sales) ...
_prints: list[dict] = []
_keys: list[int] = []
# ... and the prints IBKR reports as tape-eligible (unreported=False). Only these
# build candles, last and volume, matching IBKR's own historical bars.
_eligible: list[dict] = []
_ekeys: list[int] = []
_volumes: list[float] = []
# Running session high/low over eligible prints, parallel to _volumes.
_highs: list[float] = []
_lows: list[float] = []
_buckets: dict[int, list[dict]] = {}
_prev_close: dict[str, float | None] = {}


@synchronized
def clear():
    global _selection, _prints, _keys, _eligible, _ekeys, _volumes, _highs, _lows, _buckets
    _selection, _prints, _keys, _eligible, _ekeys, _volumes = None, [], [], [], [], []
    _highs, _lows, _buckets = [], [], {}
    _prev_close.clear()


@synchronized
def status():
    return dict(_selection) if _selection else None


@synchronized
def select(spec: dict):
    """Load reached trade coverage for the window; never creates a download job."""
    global _selection, _prints, _keys, _eligible, _ekeys, _volumes, _highs, _lows, _buckets
    from sim import replay, session_clock
    previous = _selection
    same_window = previous is not None and all(
        previous[k] == spec[k] for k in ("symbol", "date", "start", "end"))
    replay.clear_capture()
    job = store.find(spec, "trades")
    rows = ([r for r in store.read_prints(job["id"]) if r["ts"] < job["cursor"]]
            if job else [])
    eligible = [r for r in rows if not r.get("unreported")]
    volumes, highs, lows, total = [], [], [], 0
    for row in eligible:
        total += row["size"]
        volumes.append(total)
        highs.append(max(highs[-1], row["price"]) if highs else row["price"])
        lows.append(min(lows[-1], row["price"]) if lows else row["price"])
    _prints, _keys, _buckets = rows, [r["ts"] for r in rows], {}
    _eligible, _ekeys, _volumes = eligible, [r["ts"] for r in eligible], volumes
    _highs, _lows = highs, lows
    _prev_close.clear()
    _selection = dict(spec, coverage_through=job["cursor"] if job else spec["start_ts"],
                      trade_count=len(rows), download_status=job["status"] if job else "missing",
                      job_id=job["id"] if job else None)
    session_clock.set_session_date(spec["date"])
    session_clock.set_window(spec["start"], spec["end"])
    if not same_window:
        session_clock.scrub_to_second(0)  # a reload of the same window keeps the playhead
    return status()


@synchronized
def bars(symbol: str, timeframe: str, limit: int, now: datetime):
    from bars_store import read
    from sim.chart_replay import INTERVAL_SECONDS, aggregate_prints
    spec = _selection
    if not spec or timeframe not in INTERVAL_SECONDS:
        return None
    seconds = INTERVAL_SECONDS[timeframe]
    cutoff = min(now.timestamp(), spec["end_ts"])
    stored = read(symbol, timeframe, limit, from_ts=spec["start_ts"], through_ts=cutoff - seconds)
    result = (stored or {}).get("bars", [])
    # Retained downloads survive eviction of the shared chart cache.
    retained = store.read_candles(symbol, spec["start_ts"], min(cutoff, spec["end_ts"]))
    if timeframe != "1Min":
        from ibkr.historical_derive import derive_from_1min
        retained = derive_from_1min(retained, timeframe)
    merged = {datetime.fromisoformat(r["t"].replace("Z", "+00:00")).timestamp(): r for r in result}
    for row in retained:
        ts = datetime.fromisoformat(row["t"].replace("Z", "+00:00")).timestamp()
        if spec["start_ts"] <= ts and ts + seconds <= cutoff:
            merged[ts] = row
    result = list(merged.values())
    if symbol == spec["symbol"] and _prints:
        # Replace an archive bucket only if its whole reached portion is downloaded.
        coverage = spec["coverage_through"]
        result = [r for r in result if not (
            spec["start_ts"] <= datetime.fromisoformat(r["t"].replace("Z", "+00:00")).timestamp()
            and datetime.fromisoformat(r["t"].replace("Z", "+00:00")).timestamp() + seconds <= coverage)]
        if seconds not in _buckets:
            _buckets[seconds] = aggregate_prints(_eligible, seconds)
        current = int(cutoff // seconds) * seconds
        completed = [r for r in _buckets[seconds] if r["ts"] + seconds <= cutoff]
        reached = _eligible[bisect.bisect_left(_ekeys, current):bisect.bisect_right(_ekeys, min(cutoff, coverage - 1))]
        for row in completed + aggregate_prints(reached, seconds):
            if row["ts"] + seconds > coverage and cutoff >= coverage:
                continue
            result.append(dict(t=datetime.fromtimestamp(row["ts"], timezone.utc).isoformat(),
                               o=row["open"], h=row["high"], l=row["low"], c=row["close"],
                               v=row["volume"], partial=row["ts"] + seconds > cutoff))
    return sorted(result, key=lambda r: r["t"])[-limit:]


def _previous_close(symbol: str, spec: dict) -> float | None:
    """Prior trading day's regular-session close, or None when it is not stored.

    The live quote head measures change against IBKR's official close, so prefer
    the 15:59 ET minute bar; stored daily bars include extended hours
    (useRTH=False) and are only the fallback. Never use an older session.
    """
    if symbol in _prev_close:
        return _prev_close[symbol]
    from bars_store import read
    from sim.trading_day import last_trading_day
    prior = last_trading_day(date.fromisoformat(spec["date"]) - timedelta(days=1))
    last_minute = datetime.combine(prior, time(15, 59), ET).timestamp()
    daily_label = datetime.combine(prior, time(0, 0), timezone.utc).timestamp()
    for timeframe, ts in (("1Min", last_minute), ("1Day", daily_label)):
        rows = (read(symbol, timeframe, 1, from_ts=ts, through_ts=ts) or {}).get("bars") or []
        if rows:
            # Cache hits only: bars stored later in the selection still count.
            _prev_close[symbol] = float(rows[-1]["c"])
            return _prev_close[symbol]
    return None


@synchronized
def snapshot(symbol: str):
    from sim import session_clock
    spec = _selection
    if not spec:
        return {"active": False}
    now = session_clock.now_et()
    result = dict(active=True, symbol=symbol, as_of=now.isoformat(), selection=spec,
                  prints=[], last=None, volume=None, source="completed_bars",
                  open=None, high=None, low=None, prev_close=_previous_close(symbol, spec),
                  bid=None, ask=None, depth_available=False)
    if symbol == spec["symbol"] and _prints:
        end = bisect.bisect_right(_keys, now.timestamp())
        eligible_end = bisect.bisect_right(_ekeys, now.timestamp())
        reached = eligible_end - 1
        result.update(source="trades", volume=_volumes[reached] if eligible_end else 0,
                      last=_eligible[reached]["price"] if eligible_end else None,
                      open=_eligible[0]["price"] if eligible_end else None,
                      high=_highs[reached] if eligible_end else None,
                      low=_lows[reached] if eligible_end else None)
        recent = _prints[max(0, end - SIM_HISTORY_TAPE_ROWS):end]
        result["prints"] = [dict(r, time=datetime.fromtimestamp(r["ts"], timezone.utc).isoformat(),
                                 bid=None, ask=None, side=None) for r in recent][::-1]
    if result["source"] != "trades" or now.timestamp() >= spec["coverage_through"]:
        candles = bars(symbol, "1Min", 2000, now) or []
        if candles:
            result.update(last=candles[-1]["c"], volume=sum(r["v"] for r in candles),
                          open=candles[0]["o"], high=max(r["h"] for r in candles),
                          low=min(r["l"] for r in candles),
                          source="mixed" if result["prints"] else "completed_bars")
    return result
