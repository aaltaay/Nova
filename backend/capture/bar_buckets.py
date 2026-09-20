"""Roll 10s / 1m / 5m / 1d bars from prints into session Record."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

# symbol -> timeframe -> open bucket
_buckets: dict[str, dict[str, dict[str, Any]]] = {}


def reset_for_tests() -> None:
    _buckets.clear()


def _floor_ts(ts: float, step: int) -> float:
    return float(int(ts) - (int(ts) % step))


def _day_open_ts(ts: float) -> float:
    dt = datetime.fromtimestamp(ts, tz=ET)
    open_dt = dt.replace(hour=6, minute=0, second=0, microsecond=0)
    return open_dt.timestamp()


def on_print(symbol: str, ts: float, price: float, size: float, *, source: str, session_date: str) -> None:
    """Update rolling bars and emit closed buckets to the recorder."""
    try:
        from capture.recorder import record_bar
    except Exception:
        return

    sym = symbol.upper()
    by_tf = _buckets.setdefault(sym, {})

    specs = (
        ("10s", 10),
        ("1m", 60),
        ("5m", 300),
    )
    for tf, step in specs:
        bucket_ts = _floor_ts(ts, step)
        cur = by_tf.get(tf)
        if cur is None or cur["ts"] != bucket_ts:
            if cur is not None:
                record_bar(tf, cur)
            by_tf[tf] = {
                "symbol": sym,
                "ts": bucket_ts,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": size,
                "timeframe": tf,
                "source": source,
                "session_date": session_date,
            }
        else:
            cur["high"] = max(cur["high"], price)
            cur["low"] = min(cur["low"], price)
            cur["close"] = price
            cur["volume"] = float(cur["volume"]) + size

    # Full day: one bar from session open (6:00 ET) that updates continuously
    day_ts = _day_open_ts(ts)
    cur = by_tf.get("1d")
    if cur is None or cur["ts"] != day_ts:
        if cur is not None:
            record_bar("1d", cur)
        by_tf["1d"] = {
            "symbol": sym,
            "ts": day_ts,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": size,
            "timeframe": "1d",
            "source": source,
            "session_date": session_date,
        }
    else:
        cur["high"] = max(cur["high"], price)
        cur["low"] = min(cur["low"], price)
        cur["close"] = price
        cur["volume"] = float(cur["volume"]) + size
        # Upsert current day bar each print so partial days still have a usable 1d tip
        record_bar("1d", dict(cur))


def drain_open(symbol: str | None = None) -> list[tuple[str, dict[str, Any]]]:
    """Pop the open buckets and *return* them as ``(timeframe, bar)`` pairs.

    Deliberately does not call back into the recorder (D-063).  ``stop_recorder``
    runs this while holding the recorder's non-reentrant lock; the old
    ``flush_open`` called ``record_bar`` from here, which re-acquired that same
    lock on the same thread and deadlocked the FastAPI event loop on the very
    first Stop.  Returning the bars keeps the write on the caller's side of the
    lock, where it can use the internal already-locked write path.
    """
    out: list[tuple[str, dict[str, Any]]] = []
    syms = [symbol.upper()] if symbol else list(_buckets.keys())
    for sym in syms:
        by_tf = _buckets.pop(sym, None)
        if not by_tf:
            continue
        for tf, bar in by_tf.items():
            out.append((tf, bar))
    return out
