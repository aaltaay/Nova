"""Tests for momentum 5-min relative volume metrics."""
from __future__ import annotations

import random
import threading
from collections import deque

import hod_momo_metrics
from hod_momo_metrics import (
    clear_volume_buffers,
    compute_symbol_rvol_5min,
    cum_volume_at,
    cum_volume_samples,
    rvol_5min,
    tod_5min_session_fraction,
    typical_5min_volume,
    update_cum_volume,
    volume_in_window,
)


def setup_function() -> None:
    clear_volume_buffers()


def test_typical_5min_volume_flat():
    # 720 min session → 144 bars; avg 1.44M → typical 10k per 5m
    assert typical_5min_volume(1_440_000, session_minutes=720, use_tod=False) == 10_000.0


def test_rvol_5min_ratio_flat():
    assert rvol_5min(50_000, 1_440_000, session_minutes=720, use_tod=False) == 5.0


def test_tod_open_heavier_than_midday():
    open_frac = tod_5min_session_fraction(et_minute=9 * 60 + 35)
    lunch_frac = tod_5min_session_fraction(et_minute=12 * 60 + 30)
    assert open_frac > lunch_frac


def test_tod_typical_open_gt_flat_midday():
    avg = 1_440_000.0
    open_typ = typical_5min_volume(avg, use_tod=True, et_minute=9 * 60 + 35)
    lunch_typ = typical_5min_volume(avg, use_tod=True, et_minute=12 * 60 + 30)
    assert open_typ is not None and lunch_typ is not None
    assert open_typ > lunch_typ


def test_volume_in_window_from_cum_delta():
    sym = "TSSI"
    t0 = 1_000_000.0
    update_cum_volume(sym, 100_000, t0)
    update_cum_volume(sym, 120_000, t0 + 60)
    update_cum_volume(sym, 150_000, t0 + 300)
    assert volume_in_window(sym, window_sec=300, ts=t0 + 300) == 50_000
    # Flat path for deterministic ratio (TOD depends on wall clock ET)
    assert rvol_5min(50_000, 1_440_000, session_minutes=720, use_tod=False) == 5.0
    assert compute_symbol_rvol_5min(sym, 1_440_000, ts=t0 + 300) is not None


# -- the ordered series (#619) ------------------------------------------------------------------
# The deque it replaced, kept as the reference: the series must read the same on an in-order day.

def _old_update(buf: deque, v: int, ts: float, keep: float) -> None:
    if buf and buf[-1][1] == v and (ts - buf[-1][0]) < 0.5:
        return
    buf.append((ts, v))
    cutoff = ts - keep
    while buf and buf[0][0] < cutoff:
        buf.popleft()


def _old_volume_in_window(buf: deque, window: float, ts: float) -> int | None:
    if not buf or len(buf) < 2:
        return None
    current = buf[-1][1]
    cutoff = ts - window
    baseline = None
    for t, v in buf:
        if t <= cutoff:
            baseline = v
        else:
            break
    if baseline is None:
        oldest_t, oldest_v = buf[0]
        if ts - oldest_t < window * 0.5:
            return None
        baseline = oldest_v
    delta = current - baseline
    return delta if delta >= 0 else None


def test_series_reads_like_the_old_deque_over_a_long_day():
    rng = random.Random(619)
    sym = "OPEN"
    ref: deque = deque()
    ts, vol = 1_000_000.0, 50_000
    for _ in range(40_000):                 # hours of samples: it trims and compacts
        ts += rng.choice((0.05, 0.1, 0.3, 0.6, 1.0))
        if rng.random() > 0.2:              # the rest repeat, and some hit the 500 ms rule
            vol += rng.randint(1, 900)
        update_cum_volume(sym, vol, ts)
        _old_update(ref, vol, ts, hod_momo_metrics._MAX_SAMPLES_SEC)
    assert cum_volume_samples(sym) == list(ref)
    for window in (30.0, 300.0, 660.0, 3000.0):
        for back in (0.0, 5.0, 61.0, 900.0):
            assert volume_in_window(sym, window_sec=window, ts=ts - back) == _old_volume_in_window(
                ref, window, ts - back)
    for back in (0.0, 0.7, 60.0, 659.9, 3599.0, 4000.0):
        expect = next((v for t, v in reversed(ref) if t <= ts - back), None)
        assert cum_volume_at(sym, ts - back) == expect


def test_a_late_sample_lands_in_time_order():
    sym = "LATE"
    t0 = 1_000_000.0
    for i, v in enumerate((100, 200, 300, 400)):
        update_cum_volume(sym, v, t0 + 10 * i)
    update_cum_volume(sym, 250, t0 + 15)       # arrives after the +30 sample
    assert cum_volume_samples(sym) == [
        (t0, 100), (t0 + 10, 200), (t0 + 15, 250), (t0 + 20, 300), (t0 + 30, 400)]
    assert cum_volume_at(sym, t0 + 16) == 250
    assert cum_volume_at(sym, t0 - 1) is None
    assert volume_in_window(sym, window_sec=15, ts=t0 + 30) == 150


def test_reads_while_another_thread_writes():
    sym = "BUSY"
    t0 = 1_000_000.0
    errors: list[Exception] = []

    def write() -> None:
        try:
            for i in range(20_000):
                update_cum_volume(sym, 1_000 + i, t0 + i * 0.25)
        except Exception as exc:      # surfaced by the assert below
            errors.append(exc)

    writer = threading.Thread(target=write)
    writer.start()
    while writer.is_alive():
        volume_in_window(sym, window_sec=300)
        cum_volume_at(sym, t0 + 2_000.0)
    writer.join()
    assert not errors
    samples = cum_volume_samples(sym)
    assert samples == sorted(samples)
    assert samples[-1] == (t0 + 19_999 * 0.25, 20_999)
