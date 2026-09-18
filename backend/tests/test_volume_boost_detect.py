"""Pure Volume boost spike math -- no IBKR, no FastAPI."""
from __future__ import annotations

from volume_boost_detect import measure_spike, step_tracker


SPIKE_SEC = 60.0
BASELINE_SEC = 600.0
MIN_SPIKE = 10_000
MIN_BASELINE = 5_000
ENTER = 5.0
EXIT = 2.5
DEBOUNCE = 3.0


def _samples_flat_then_spike(
    *,
    baseline_shares: int = 12_000,
    spike_shares: int = 80_000,
    t0: float = 1_000_000.0,
) -> tuple[list[tuple[float, int]], float]:
    """10 minutes of even prints, then a 60s dump. Returns (samples, now)."""
    samples: list[tuple[float, int]] = []
    vol = 100_000
    # One sample per 60s across the baseline window.
    steps = int(BASELINE_SEC // 60)
    per_step = baseline_shares // steps
    for i in range(steps + 1):
        samples.append((t0 + i * 60.0, vol))
        if i < steps:
            vol += per_step
    now = t0 + BASELINE_SEC + SPIKE_SEC
    samples.append((now, vol + spike_shares))
    return samples, now


def test_measure_spike_flags_exceptional_rate():
    samples, now = _samples_flat_then_spike()
    metrics = measure_spike(
        samples,
        now,
        spike_sec=SPIKE_SEC,
        baseline_sec=BASELINE_SEC,
        min_spike_shares=MIN_SPIKE,
        min_baseline_shares=MIN_BASELINE,
    )
    assert metrics is not None
    assert metrics.spike_shares == 80_000
    assert metrics.baseline_shares >= MIN_BASELINE
    assert metrics.ratio >= ENTER


def test_measure_spike_none_without_history():
    now = 50.0
    samples = [(40.0, 100_000), (50.0, 200_000)]
    assert (
        measure_spike(
            samples,
            now,
            spike_sec=SPIKE_SEC,
            baseline_sec=BASELINE_SEC,
            min_spike_shares=MIN_SPIKE,
            min_baseline_shares=MIN_BASELINE,
        )
        is None
    )


def test_measure_spike_none_when_spike_shares_tiny():
    samples, now = _samples_flat_then_spike(spike_shares=400)
    assert (
        measure_spike(
            samples,
            now,
            spike_sec=SPIKE_SEC,
            baseline_sec=BASELINE_SEC,
            min_spike_shares=MIN_SPIKE,
            min_baseline_shares=MIN_BASELINE,
        )
        is None
    )


def test_measure_spike_none_on_negative_cum_reset():
    t0 = 1_000_000.0
    samples = [(t0, 500_000), (t0 + 600.0, 520_000), (t0 + 660.0, 10_000)]
    assert (
        measure_spike(
            samples,
            t0 + 660.0,
            spike_sec=SPIKE_SEC,
            baseline_sec=BASELINE_SEC,
            min_spike_shares=MIN_SPIKE,
            min_baseline_shares=MIN_BASELINE,
        )
        is None
    )


def test_debounce_rejects_one_shot_blip():
    samples, now = _samples_flat_then_spike()
    metrics = measure_spike(
        samples,
        now,
        spike_sec=SPIKE_SEC,
        baseline_sec=BASELINE_SEC,
        min_spike_shares=MIN_SPIKE,
        min_baseline_shares=MIN_BASELINE,
    )
    assert metrics is not None
    pending = step_tracker(
        None,
        metrics,
        now,
        enter=ENTER,
        exit_ratio=EXIT,
        debounce_sec=DEBOUNCE,
    )
    assert pending is not None
    assert pending.admitted_at is None
    # Drops below enter before debounce elapses -- no row.
    quiet, quiet_now = _samples_flat_then_spike(spike_shares=1_000)
    quiet_metrics = measure_spike(
        quiet,
        quiet_now,
        spike_sec=SPIKE_SEC,
        baseline_sec=BASELINE_SEC,
        min_spike_shares=MIN_SPIKE,
        min_baseline_shares=MIN_BASELINE,
    )
    assert (
        step_tracker(
            pending,
            quiet_metrics,
            now + 1.0,
            enter=ENTER,
            exit_ratio=EXIT,
            debounce_sec=DEBOUNCE,
        )
        is None
    )


def test_debounce_admits_after_hold():
    samples, now = _samples_flat_then_spike()
    metrics = measure_spike(
        samples,
        now,
        spike_sec=SPIKE_SEC,
        baseline_sec=BASELINE_SEC,
        min_spike_shares=MIN_SPIKE,
        min_baseline_shares=MIN_BASELINE,
    )
    pending = step_tracker(
        None,
        metrics,
        now,
        enter=ENTER,
        exit_ratio=EXIT,
        debounce_sec=DEBOUNCE,
    )
    admitted = step_tracker(
        pending,
        metrics,
        now + DEBOUNCE,
        enter=ENTER,
        exit_ratio=EXIT,
        debounce_sec=DEBOUNCE,
    )
    assert admitted is not None
    assert admitted.admitted_at == now
    assert admitted.cooling is False


def test_cool_off_hysteresis_then_drop():
    samples, now = _samples_flat_then_spike()
    hot = measure_spike(
        samples,
        now,
        spike_sec=SPIKE_SEC,
        baseline_sec=BASELINE_SEC,
        min_spike_shares=MIN_SPIKE,
        min_baseline_shares=MIN_BASELINE,
    )
    tracker = step_tracker(
        None, hot, now, enter=ENTER, exit_ratio=EXIT, debounce_sec=0.0
    )
    assert tracker is not None and tracker.admitted_at is not None

    mid, mid_now = _samples_flat_then_spike(
        baseline_shares=80_000,
        spike_shares=35_000,
    )
    mid_metrics = measure_spike(
        mid,
        mid_now,
        spike_sec=SPIKE_SEC,
        baseline_sec=BASELINE_SEC,
        min_spike_shares=8_000,
        min_baseline_shares=MIN_BASELINE,
    )
    assert mid_metrics is not None
    assert EXIT <= mid_metrics.ratio < ENTER
    cooling = step_tracker(
        tracker,
        mid_metrics,
        now + 10.0,
        enter=ENTER,
        exit_ratio=EXIT,
        debounce_sec=DEBOUNCE,
    )
    assert cooling is not None
    assert cooling.cooling is True
    assert cooling.admitted_at == tracker.admitted_at

    dead, dead_now = _samples_flat_then_spike(
        baseline_shares=80_000,
        spike_shares=12_000,
    )
    dead_metrics = measure_spike(
        dead,
        dead_now,
        spike_sec=SPIKE_SEC,
        baseline_sec=BASELINE_SEC,
        min_spike_shares=1_000,
        min_baseline_shares=MIN_BASELINE,
    )
    assert dead_metrics is not None
    assert dead_metrics.ratio < EXIT
    assert (
        step_tracker(
            cooling,
            dead_metrics,
            now + 20.0,
            enter=ENTER,
            exit_ratio=EXIT,
            debounce_sec=DEBOUNCE,
        )
        is None
    )
