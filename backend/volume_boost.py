"""Volume boost -- exceptional L1 volume-rate spikes on the existing watch.

Owner: this module. State is in-memory only (session process). Invalidation:
IB reconnect / process start / ``reset_for_tests``. No disk cache.

Observes day-volume already delivered on the shared ``reqMktData`` line
(``ibkr.l1_apply.apply_l1_quote``). Does not open ticks, leases, or HOD seats.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from constants import (
    NOVA_API_REV,
    VOLUME_BOOST_BASELINE_WINDOW_SEC,
    VOLUME_BOOST_DEBOUNCE_SEC,
    VOLUME_BOOST_ENTER_RATIO,
    VOLUME_BOOST_EXIT_RATIO,
    VOLUME_BOOST_MIN_BASELINE_SHARES,
    VOLUME_BOOST_MIN_SPIKE_SHARES,
    VOLUME_BOOST_SPIKE_WINDOW_SEC,
    VOLUME_BOOST_STALE_SEC,
    VOLUME_BOOST_TOP_N,
)
from hod_momo_metrics import cum_volume_samples, update_cum_volume
from volume_boost_detect import SpikeTracker, measure_spike, step_tracker

logger = logging.getLogger(__name__)

_trackers: dict[str, SpikeTracker] = {}
_watched: set[str] = set()


def reset_for_tests() -> None:
    _trackers.clear()
    _watched.clear()


def observe_l1(
    symbol: str,
    cum_volume: int | None,
    price: float | None,
    ts: float,
) -> None:
    """Record one existing L1 day-volume print and refresh that symbol."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return
    now = float(ts)
    update_cum_volume(sym, cum_volume, now)
    _watched.add(sym)
    metrics = measure_spike(
        cum_volume_samples(sym),
        now,
        spike_sec=VOLUME_BOOST_SPIKE_WINDOW_SEC,
        baseline_sec=VOLUME_BOOST_BASELINE_WINDOW_SEC,
        min_spike_shares=VOLUME_BOOST_MIN_SPIKE_SHARES,
        min_baseline_shares=VOLUME_BOOST_MIN_BASELINE_SHARES,
    )
    nxt = step_tracker(
        _trackers.get(sym),
        metrics,
        now,
        enter=VOLUME_BOOST_ENTER_RATIO,
        exit_ratio=VOLUME_BOOST_EXIT_RATIO,
        debounce_sec=VOLUME_BOOST_DEBOUNCE_SEC,
    )
    if nxt is None:
        _trackers.pop(sym, None)
        return
    if price is not None:
        try:
            px = float(price)
        except (TypeError, ValueError):
            px = None
        if px is not None and px > 0:
            nxt.price = px
    _trackers[sym] = nxt


def _expire_stale(now: float) -> None:
    cutoff = now - VOLUME_BOOST_STALE_SEC
    dead = [sym for sym, tr in _trackers.items() if tr.last_seen_ts < cutoff]
    for sym in dead:
        _trackers.pop(sym, None)


def _ibkr_ready() -> bool:
    try:
        from ibkr.client import is_ready

        return bool(is_ready())
    except Exception:
        logger.debug("volume_boost: ibkr ready check failed", exc_info=True)
        return False


def _bridge_error() -> str | None:
    try:
        from runtime_state import get_runtime_state

        err = (getattr(get_runtime_state(), "ibkr_bridge_last_error", "") or "").strip()
        return err or None
    except Exception:
        logger.debug("volume_boost: bridge error read failed", exc_info=True)
        return None


def _row(sym: str, tracker: SpikeTracker, now: float) -> dict[str, Any]:
    started = tracker.admitted_at if tracker.admitted_at is not None else tracker.first_above_enter_ts
    age = None if started is None else max(0.0, now - started)
    return {
        "symbol": sym,
        "price": tracker.price,
        "spike_ratio": tracker.last_ratio,
        "spike_shares": tracker.last_spike_shares,
        "baseline_shares": tracker.last_baseline_shares,
        "baseline_rate": tracker.last_baseline_rate,
        "status": "cooling" if tracker.cooling else "hot",
        "spike_started_ts": started,
        "age_sec": round(age, 1) if age is not None else None,
    }


def build_view(now: float | None = None) -> dict[str, Any]:
    """REST snapshot. Empty + IBKR ready is honest; empty + down is loud."""
    ts = time.time() if now is None else float(now)
    _expire_stale(ts)
    rows = [
        _row(sym, tr, ts)
        for sym, tr in _trackers.items()
        if tr.admitted_at is not None
    ]
    rows.sort(key=lambda r: float(r.get("spike_ratio") or 0.0), reverse=True)
    rows = rows[: VOLUME_BOOST_TOP_N]
    ready = _ibkr_ready()
    bridge_err = _bridge_error()
    feed_error = None
    if not ready:
        feed_error = (
            bridge_err
            or "IBKR is not ready -- Volume boost watches existing L1 only."
        )
    table_state = "live" if ready else "unavailable"
    return {
        "rev": NOVA_API_REV,
        "volume_boost": rows,
        "table_state": table_state,
        "last_scan": ts,
        "feed_error": feed_error,
        "watched": len(_watched),
        "windows": {
            "spike_sec": VOLUME_BOOST_SPIKE_WINDOW_SEC,
            "baseline_sec": VOLUME_BOOST_BASELINE_WINDOW_SEC,
            "enter_ratio": VOLUME_BOOST_ENTER_RATIO,
            "exit_ratio": VOLUME_BOOST_EXIT_RATIO,
            "top_n": VOLUME_BOOST_TOP_N,
        },
    }
