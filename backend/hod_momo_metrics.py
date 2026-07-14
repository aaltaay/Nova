"""HOD Momo volume metrics — Warrior 5-min relative volume.

Warrior Day Trade Dash shows Relative Volume (5 min %): volume in the last
5 minutes vs a typical 5-minute interval (avg daily ÷ bars-per-session).

IBKR table ticks and Alpaca enrichment expose *cumulative* day volume, not
per-print size. We sample (ts, cum_vol) and take the delta over the window.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime

from constants import (
    HOD_MOMO_RVOL_5MIN_SESSION_MINUTES,
    HOD_MOMO_RVOL_5MIN_WINDOW_SEC,
)

# symbol -> deque[(unix_ts, cumulative_day_volume)]
_cum_volume_buffer: dict[str, deque[tuple[float, int]]] = {}
_MAX_SAMPLES_SEC = 3600  # keep 1h of cum-vol samples


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


def typical_5min_volume(avg_daily_vol: float, session_minutes: float | None = None) -> float | None:
    """Expected volume in one 5-minute bar given average daily volume."""
    try:
        avg = float(avg_daily_vol)
    except (TypeError, ValueError):
        return None
    if avg <= 0:
        return None
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
    typical = typical_5min_volume(avg_daily_vol, session_minutes)
    if typical is None or typical <= 0:
        return None
    return round(v5 / typical, 2)


def compute_symbol_rvol_5min(
    symbol: str,
    avg_daily_vol: float | None,
    ts: float | None = None,
) -> float | None:
    """Convenience: window volume + pace against avg daily."""
    return rvol_5min(volume_in_window(symbol, ts=ts), avg_daily_vol)
