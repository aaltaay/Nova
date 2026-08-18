"""Derive coarser intraday bars from 1-minute IBKR bars.

A 1Min / 1 D pull covers today's 5Min / 15Min / 30Min / 1Hour panes.
Longer native spans (5 D of 5Min, 5 Y of 1Day) still need their own fetch;
derived series are an honest first paint, not a replacement.
"""
from __future__ import annotations

from datetime import datetime, timezone

BUCKET_SEC: dict[str, int] = {
    "5Min": 300,
    "15Min": 900,
    "30Min": 1800,
    "1Hour": 3600,
}

DERIVE_FROM_1MIN: frozenset[str] = frozenset(BUCKET_SEC)


def bar_unix(bar: dict) -> float | None:
    raw = bar.get("t")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        ts = float(raw)
        return ts / 1000.0 if ts > 1e12 else ts
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def unix_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def derive_from_1min(bars: list[dict], target_tf: str) -> list[dict]:
    """Aggregate 1Min OHLCV into ``target_tf``. Empty if the target is not derived."""
    size = BUCKET_SEC.get(target_tf)
    if not size or not bars:
        return []
    buckets: dict[int, dict] = {}
    order: list[int] = []
    for bar in bars:
        ts = bar_unix(bar)
        if ts is None:
            continue
        try:
            open_ = float(bar["o"])
            high = float(bar["h"])
            low = float(bar["l"])
            close = float(bar["c"])
            volume = int(bar.get("v") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        key = int(ts // size) * size
        existing = buckets.get(key)
        if existing is None:
            buckets[key] = {
                "t": unix_to_iso(float(key)),
                "o": open_,
                "h": high,
                "l": low,
                "c": close,
                "v": volume,
            }
            order.append(key)
            continue
        existing["h"] = max(existing["h"], high)
        existing["l"] = min(existing["l"], low)
        existing["c"] = close
        existing["v"] += volume
    return [buckets[key] for key in order]
