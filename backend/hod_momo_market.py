"""HOD Momo market snapshots, surge buffers, and fundamentals queue."""
from __future__ import annotations

import time
from collections import deque
from typing import Any

import hod_momo_flow as _flow
import hod_momo_metrics as _metrics
import hod_momo_state as _state
import market as _market
from constants import HOD_MOMO_INTEGRITY_SURGE_MIN_SPAN_SEC
from hod_momo_filters import price_surge as _price_surge
from hod_momo_models import TickerSnap

_MAX_BUFFER_MINUTES = 60


def in_premarket_et() -> bool:
    """Delegate to market.py — same SESSION_* constants as chart shading."""
    return _market.in_premarket()


def in_afterhours_et() -> bool:
    """Delegate to market.py — same SESSION_* constants as chart shading."""
    return _market.in_after_hours()


def effective_min_rvol() -> float:
    master = _state.get_state().master
    if in_afterhours_et():
        return master.afterhours_min_rvol
    if in_premarket_et():
        return master.premarket_min_rvol
    return master.min_rvol


def update_price_buffer(symbol: str, price: float, ts: float) -> None:
    state = _state.get_state()
    buf = state.price_buffer.setdefault(symbol, deque())
    buf.append((ts, price))
    cutoff = ts - _MAX_BUFFER_MINUTES * 60
    while buf and buf[0][0] < cutoff:
        buf.popleft()


def request_surge_seed(symbol: str) -> None:
    state = _state.get_state()
    sym = (symbol or "").strip().upper()
    if (
        not sym
        or sym in state.surge_seeded
        or sym in state.pending_surge_seed
    ):
        return
    state.pending_surge_seed.add(sym)


def pop_pending_surge_seeds(limit: int) -> list[str]:
    state = _state.get_state()
    out: list[str] = []
    for sym in list(state.pending_surge_seed):
        if len(out) >= max(0, int(limit)):
            break
        state.pending_surge_seed.discard(sym)
        out.append(sym)
    return out


def mark_surge_seed_attempted(symbol: str) -> None:
    state = _state.get_state()
    sym = (symbol or "").strip().upper()
    if not sym:
        return
    state.pending_surge_seed.discard(sym)
    state.surge_seeded.add(sym)


def seed_price_buffer(symbol: str, points: list[tuple[float, float]]) -> int:
    state = _state.get_state()
    sym = (symbol or "").strip().upper()
    if not sym:
        return 0
    buf = state.price_buffer.setdefault(sym, deque())
    existing = {(float(ts), float(price)) for ts, price in buf}
    added = 0
    for ts, price in points or []:
        try:
            point_ts = float(ts)
            point_price = float(price)
        except (TypeError, ValueError):
            continue
        if point_price <= 0:
            continue
        key = (point_ts, point_price)
        if key in existing:
            continue
        buf.append(key)
        existing.add(key)
        added += 1
    if buf:
        ordered = sorted(buf, key=lambda item: item[0])
        buf.clear()
        buf.extend(ordered)
        cutoff = buf[-1][0] - _MAX_BUFFER_MINUTES * 60
        while buf and buf[0][0] < cutoff:
            buf.popleft()
    mark_surge_seed_attempted(sym)
    return added


def reevaluate_after_surge_seed(symbol: str) -> None:
    sym = (symbol or "").strip().upper()
    snap = _state.get_state().ticker_snaps.get(sym)
    if snap is None or not snap.price:
        return
    from hod_momo_trade import on_trade_update

    on_trade_update(sym, float(snap.price), time.time(), volume=snap.volume)


def get_flow_stats() -> dict[str, Any]:
    state = _state.get_state()
    ready_n, buffer_n = _flow.count_surge_ready(
        state.price_buffer,
        HOD_MOMO_INTEGRITY_SURGE_MIN_SPAN_SEC,
    )
    rvol_n = sum(1 for snap in state.ticker_snaps.values() if snap.rvol is not None)
    uptime = (time.monotonic() - state.startup_ts) if state.startup_ts else 0.0
    last_age = (
        time.time() - state.last_trade_ts if state.last_trade_ts else None
    )
    surge_none = _flow.count_surge_none_after_seed(
        seeded=state.surge_seeded,
        price_buffer=state.price_buffer,
        ticker_snaps=state.ticker_snaps,
        surge_fn=_price_surge,
    )
    return {
        "total_trades_seen": state.total_trades_seen,
        "last_trade_age_sec": last_age,
        "process_uptime_sec": uptime,
        "buffer_symbol_count": buffer_n,
        "surge_ready_count": ready_n,
        "surge_seeded_count": len(state.surge_seeded),
        "pending_surge_seeds": len(state.pending_surge_seed),
        "surge_none_after_seed_count": surge_none,
        "snaps_with_rvol": rvol_n,
        "snaps_tracked": len(state.ticker_snaps),
    }


def update_ticker_snapshot(
    symbol: str,
    price: float,
    rvol: float | None = None,
    float_shares: float | None = None,
    gap_pct: float | None = None,
    volume: int | None = None,
    change_pct: float | None = None,
    fifty_two_week_high: float | None = None,
    rvol_source: str | None = None,
    avg_volume: float | None = None,
    rvol_5min: float | None = None,
) -> None:
    snap = _state.get_state().ticker_snaps.setdefault(symbol, TickerSnap())
    snap.price = price
    if rvol is not None:
        snap.rvol = rvol
    if float_shares is not None:
        snap.float_shares = float_shares
    if gap_pct is not None:
        snap.gap_pct = gap_pct
    if volume is not None:
        snap.volume = volume
        _metrics.update_cum_volume(symbol, volume, time.time())
    if change_pct is not None:
        snap.change_pct = change_pct
    if fifty_two_week_high is not None:
        snap.fifty_two_week_high = fifty_two_week_high
    if rvol_source is not None:
        snap.rvol_source = rvol_source
    if avg_volume is not None:
        snap.avg_volume = avg_volume
    if rvol_5min is not None:
        snap.rvol_5min = rvol_5min
    elif snap.avg_volume is not None:
        snap.rvol_5min = _metrics.compute_symbol_rvol_5min(
            symbol,
            snap.avg_volume,
        )
    snap.last_enriched = time.monotonic()


def get_ticker_snapshot(symbol: str) -> TickerSnap | None:
    return _state.get_state().ticker_snaps.get(symbol.upper())


def mark_needs_fundamentals(symbol: str) -> None:
    state = _state.get_state()
    if symbol not in state.fundamentals_queued:
        state.fundamentals_queued.add(symbol)
        state.fundamentals_queue.append(symbol)


def get_fundamentals_queue() -> deque[str]:
    return _state.get_state().fundamentals_queue


def pop_fundamentals_request() -> str | None:
    state = _state.get_state()
    try:
        sym = state.fundamentals_queue.popleft()
    except IndexError:
        return None
    state.fundamentals_queued.discard(sym)
    return sym


def active_symbol() -> str:
    return _state.get_state().active_symbol_name


def peek_rvol_5min(symbol: str) -> float | None:
    snap = get_ticker_snapshot(symbol)
    return snap.rvol_5min if snap else None
