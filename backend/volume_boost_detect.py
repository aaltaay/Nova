"""Pure Volume boost math -- last-window rate vs prior baseline.

No IBKR, no module state. Engine feeds observed L1 cum-vol samples.
Do not invent shares: missing coverage or a day-volume reset returns None.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpikeMetrics:
    ratio: float
    spike_shares: int
    baseline_shares: int
    spike_rate: float
    baseline_rate: float


@dataclass
class SpikeTracker:
    first_above_enter_ts: float | None = None
    admitted_at: float | None = None
    last_ratio: float | None = None
    last_spike_shares: int | None = None
    last_baseline_shares: int | None = None
    last_baseline_rate: float | None = None
    cooling: bool = False
    last_seen_ts: float = 0.0
    price: float | None = None


def _cum_at_or_before(samples: list[tuple[float, int]], ts: float) -> int | None:
    last: int | None = None
    for t, v in samples:
        if t <= ts:
            last = int(v)
        else:
            break
    return last


def measure_spike(
    samples: list[tuple[float, int]],
    now: float,
    *,
    spike_sec: float,
    baseline_sec: float,
    min_spike_shares: int,
    min_baseline_shares: int,
) -> SpikeMetrics | None:
    """Shares in the spike window vs the prior baseline window.

    Requires a cum-vol sample at or before each window edge. A drop in
    cumulative day volume is a session reset -- not a spike.
    """
    if not samples or spike_sec <= 0 or baseline_sec <= 0:
        return None
    ordered = sorted(samples, key=lambda row: row[0])
    spike_start = now - float(spike_sec)
    baseline_start = spike_start - float(baseline_sec)
    cum_end = _cum_at_or_before(ordered, now)
    cum_spike = _cum_at_or_before(ordered, spike_start)
    cum_base = _cum_at_or_before(ordered, baseline_start)
    if cum_end is None or cum_spike is None or cum_base is None:
        return None
    spike_shares = cum_end - cum_spike
    baseline_shares = cum_spike - cum_base
    if spike_shares < int(min_spike_shares) or baseline_shares < int(min_baseline_shares):
        return None
    spike_rate = spike_shares / float(spike_sec)
    baseline_rate = baseline_shares / float(baseline_sec)
    if baseline_rate <= 0:
        return None
    ratio = spike_rate / baseline_rate
    if ratio <= 0:
        return None
    return SpikeMetrics(
        ratio=round(ratio, 2),
        spike_shares=int(spike_shares),
        baseline_shares=int(baseline_shares),
        spike_rate=spike_rate,
        baseline_rate=baseline_rate,
    )


def step_tracker(
    tracker: SpikeTracker | None,
    metrics: SpikeMetrics | None,
    now: float,
    *,
    enter: float,
    exit_ratio: float,
    debounce_sec: float,
) -> SpikeTracker | None:
    """Debounce entry and hysteresis cool-off. None means drop the name."""
    if metrics is None:
        if tracker is not None and tracker.admitted_at is not None:
            tracker.last_seen_ts = now
            return tracker
        return None

    def _copy(*, admitted_at: float | None, first: float | None, cooling: bool) -> SpikeTracker:
        prev_price = tracker.price if tracker is not None else None
        return SpikeTracker(
            first_above_enter_ts=first,
            admitted_at=admitted_at,
            last_ratio=metrics.ratio,
            last_spike_shares=metrics.spike_shares,
            last_baseline_shares=metrics.baseline_shares,
            last_baseline_rate=metrics.baseline_rate,
            cooling=cooling,
            last_seen_ts=now,
            price=prev_price,
        )

    if metrics.ratio >= enter:
        first = (
            tracker.first_above_enter_ts
            if tracker is not None and tracker.first_above_enter_ts is not None
            else now
        )
        admitted = tracker.admitted_at if tracker is not None else None
        if admitted is None and (now - first) >= debounce_sec:
            admitted = first
        return _copy(admitted_at=admitted, first=first, cooling=False)

    if (
        tracker is not None
        and tracker.admitted_at is not None
        and metrics.ratio >= exit_ratio
    ):
        return _copy(
            admitted_at=tracker.admitted_at,
            first=tracker.first_above_enter_ts,
            cooling=True,
        )
    return None
