"""HOD Momo volume metrics — momentum 5-min relative volume.

momentum shows Relative Volume (5 min %): volume in the last
5 minutes vs a typical 5-minute interval.

Default typical uses a coarse ET time-of-day curve (open/close heavy). Flat
avg_daily / bars_per_session remains available when TOD is disabled.

The cumulative day-volume samples are read on every Level 1 tick (Volume boost,
HOD Momo's 5-min RVOL), so a read is a binary search, never a scan (#619: at
the 09:30 open, scanning an hour of samples per tick stalled the IB loop). The
samples stay in time order and are written from more than one thread (the IB
loop, the quote panel's REST route), so every access holds one lock.
"""
from __future__ import annotations

import threading
from array import array
from bisect import bisect_left, bisect_right
from datetime import datetime
from zoneinfo import ZoneInfo

from constants import (
    HOD_MOMO_RVOL_5MIN_SESSION_MINUTES,
    HOD_MOMO_RVOL_5MIN_TOD_CUM_FRAC,
    HOD_MOMO_RVOL_5MIN_USE_TOD,
    HOD_MOMO_RVOL_5MIN_WINDOW_SEC,
)

_MAX_SAMPLES_SEC = 3600  # keep 1h of cum-vol samples
_COMPACT_AT = 4096       # drop trimmed samples once this many have piled up at the front
_ET = ZoneInfo("America/New_York")


class _CumSeries:
    """One symbol's (unix_ts, cumulative_day_volume) samples, oldest first.

    Two flat arrays share one index; ``head`` is the first live sample. Trimming
    moves ``head``, and the dead front is dropped in one slice once it is large.
    """

    __slots__ = ("ts", "vol", "head")

    def __init__(self) -> None:
        self.ts = array("d")
        self.vol = array("q")
        self.head = 0

    def __len__(self) -> int:
        return len(self.ts) - self.head

    def add(self, ts: float, v: int) -> None:
        if len(self) and ts < self.ts[-1]:
            i = bisect_right(self.ts, ts, lo=self.head)   # rare: a late sample keeps time order
            self.ts.insert(i, ts)
            self.vol.insert(i, v)
        else:
            self.ts.append(ts)
            self.vol.append(v)

    def trim(self, cutoff: float) -> None:
        """Drop the samples older than ``cutoff``."""
        self.head = bisect_left(self.ts, cutoff, lo=self.head)
        if self.head >= _COMPACT_AT and self.head * 2 >= len(self.ts):
            del self.ts[: self.head]
            del self.vol[: self.head]
            self.head = 0

    def at_or_before(self, ts: float) -> int | None:
        i = bisect_right(self.ts, ts, lo=self.head) - 1
        return int(self.vol[i]) if i >= self.head else None


# symbol -> its samples
_cum_volume_buffer: dict[str, _CumSeries] = {}
_lock = threading.Lock()


def clear_volume_buffers() -> None:
    with _lock:
        _cum_volume_buffer.clear()


def cum_volume_samples(symbol: str) -> list[tuple[float, int]]:
    """Oldest-first L1 day-volume samples, for tests and debugging (a copy)."""
    with _lock:
        s = _cum_volume_buffer.get(symbol)
        if not s:
            return []
        return [(s.ts[i], int(s.vol[i])) for i in range(s.head, len(s.ts))]


def update_cum_volume(symbol: str, cum_volume: int | None, ts: float) -> None:
    """Record a cumulative day-volume sample (skip None / non-positive)."""
    if cum_volume is None:
        return
    try:
        v = int(cum_volume)
    except (TypeError, ValueError):
        return
    if v < 0:
        return
    ts = float(ts)
    with _lock:
        s = _cum_volume_buffer.get(symbol)
        if s is None:
            s = _cum_volume_buffer[symbol] = _CumSeries()
        if len(s) and s.vol[-1] == v and (ts - s.ts[-1]) < 0.5:
            return  # ignore duplicate spam within 500ms
        s.add(ts, v)
        s.trim(ts - _MAX_SAMPLES_SEC)


def cum_volume_at(symbol: str, ts: float) -> int | None:
    """The cumulative day volume of the last sample at or before ``ts``, or None."""
    with _lock:
        s = _cum_volume_buffer.get(symbol)
        return s.at_or_before(float(ts)) if s else None


def volume_in_window(symbol: str, window_sec: float | None = None, ts: float | None = None) -> int | None:
    """Shares traded in the last ``window_sec`` from cumulative-volume deltas."""
    with _lock:
        s = _cum_volume_buffer.get(symbol)
        if not s or len(s) < 2:
            return None
        window = float(window_sec if window_sec is not None else HOD_MOMO_RVOL_5MIN_WINDOW_SEC)
        now_ts = ts if ts is not None else s.ts[-1]
        current = int(s.vol[-1])
        baseline = s.at_or_before(now_ts - window)
        if baseline is None:
            # Not enough history — use oldest sample if it is within ~2x window
            oldest_t, oldest_v = s.ts[s.head], int(s.vol[s.head])
            if now_ts - oldest_t < window * 0.5:
                return None
            baseline = oldest_v
    delta = current - baseline
    return delta if delta >= 0 else None


def _et_minute_of_day(ts: float | None) -> int:
    if ts is None:
        dt = datetime.now(_ET)
    else:
        dt = datetime.fromtimestamp(ts, tz=_ET)
    return dt.hour * 60 + dt.minute


def tod_cum_frac(et_minute: int) -> float:
    """Interpolate cumulative daily volume fraction at ET minute-of-day."""
    knots = HOD_MOMO_RVOL_5MIN_TOD_CUM_FRAC
    if not knots:
        return 0.0
    if et_minute <= knots[0][0]:
        return float(knots[0][1])
    if et_minute >= knots[-1][0]:
        return float(knots[-1][1])
    for i in range(1, len(knots)):
        m0, f0 = knots[i - 1]
        m1, f1 = knots[i]
        if et_minute <= m1:
            if m1 == m0:
                return float(f1)
            t = (et_minute - m0) / (m1 - m0)
            return float(f0 + t * (f1 - f0))
    return float(knots[-1][1])


def tod_5min_session_fraction(et_minute: int | None = None, ts: float | None = None) -> float:
    """Expected share of daily volume in the next 5 ET minutes at this clock time."""
    minute = et_minute if et_minute is not None else _et_minute_of_day(ts)
    start = tod_cum_frac(minute)
    end = tod_cum_frac(minute + 5)
    frac = end - start
    # Floor so lunch never goes to ~0 (would explode RVOL).
    flat = 5.0 / float(HOD_MOMO_RVOL_5MIN_SESSION_MINUTES)
    return max(frac, flat * 0.35)


def typical_5min_volume(
    avg_daily_vol: float,
    session_minutes: float | None = None,
    *,
    use_tod: bool | None = None,
    ts: float | None = None,
    et_minute: int | None = None,
) -> float | None:
    """Expected volume in one 5-minute bar given average daily volume."""
    try:
        avg = float(avg_daily_vol)
    except (TypeError, ValueError):
        return None
    if avg <= 0:
        return None
    tod = HOD_MOMO_RVOL_5MIN_USE_TOD if use_tod is None else use_tod
    if tod:
        return avg * tod_5min_session_fraction(et_minute=et_minute, ts=ts)
    mins = float(session_minutes if session_minutes is not None else HOD_MOMO_RVOL_5MIN_SESSION_MINUTES)
    if mins <= 0:
        return None
    bars = mins / 5.0
    if bars <= 0:
        return None
    return avg / bars


def rvol_5min(
    vol_5m: float | None,
    avg_daily_vol: float | None,
    session_minutes: float | None = None,
    *,
    use_tod: bool | None = None,
    ts: float | None = None,
) -> float | None:
    """momentum Rel Vol (5 min): last-5m volume ÷ typical 5m volume."""
    if vol_5m is None or avg_daily_vol is None:
        return None
    try:
        v5 = float(vol_5m)
    except (TypeError, ValueError):
        return None
    if v5 <= 0:
        return None
    typical = typical_5min_volume(
        avg_daily_vol, session_minutes, use_tod=use_tod, ts=ts
    )
    if typical is None or typical <= 0:
        return None
    return round(v5 / typical, 2)


def compute_symbol_rvol_5min(
    symbol: str,
    avg_daily_vol: float | None,
    ts: float | None = None,
) -> float | None:
    """Convenience: window volume + pace against avg daily (TOD-aware)."""
    return rvol_5min(volume_in_window(symbol, ts=ts), avg_daily_vol, ts=ts)
