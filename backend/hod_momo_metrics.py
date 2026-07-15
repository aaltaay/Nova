"""HOD Momo volume metrics — Warrior 5-min relative volume.

Warrior Day Trade Dash shows Relative Volume (5 min %): volume in the last
5 minutes vs a typical 5-minute interval.

Default typical uses a coarse ET time-of-day curve (open/close heavy). Flat
avg_daily / bars_per_session remains available when TOD is disabled.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo

from constants import (
    HOD_MOMO_RVOL_5MIN_SESSION_MINUTES,
    HOD_MOMO_RVOL_5MIN_TOD_CUM_FRAC,
    HOD_MOMO_RVOL_5MIN_USE_TOD,
    HOD_MOMO_RVOL_5MIN_WINDOW_SEC,
)

# symbol -> deque[(unix_ts, cumulative_day_volume)]
_cum_volume_buffer: dict[str, deque[tuple[float, int]]] = {}
_MAX_SAMPLES_SEC = 3600  # keep 1h of cum-vol samples
_ET = ZoneInfo("America/New_York")


def clear_volume_buffers() -> None:
    _cum_volume_buffer.clear()


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
    buf = _cum_volume_buffer.setdefault(symbol, deque())
    if buf and buf[-1][1] == v and (ts - buf[-1][0]) < 0.5:
        return  # ignore duplicate spam within 500ms
    buf.append((ts, v))
    cutoff = ts - _MAX_SAMPLES_SEC
    while buf and buf[0][0] < cutoff:
        buf.popleft()


def volume_in_window(symbol: str, window_sec: float | None = None, ts: float | None = None) -> int | None:
    """Shares traded in the last ``window_sec`` from cumulative-volume deltas."""
    buf = _cum_volume_buffer.get(symbol)
    if not buf or len(buf) < 2:
        return None
    window = float(window_sec if window_sec is not None else HOD_MOMO_RVOL_5MIN_WINDOW_SEC)
    now_ts = ts if ts is not None else buf[-1][0]
    current = buf[-1][1]
    cutoff = now_ts - window
    baseline = None
    for t, v in buf:
        if t <= cutoff:
            baseline = v
        else:
            break
    if baseline is None:
        # Not enough history — use oldest sample if it is within ~2x window
        oldest_t, oldest_v = buf[0]
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
    """Warrior Rel Vol (5 min): last-5m volume ÷ typical 5m volume."""
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
