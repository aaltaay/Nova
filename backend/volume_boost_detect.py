"""Pure Volume boost math -- last-window rate vs prior baseline.

No IBKR, no module state. Engine feeds observed L1 cum-vol samples.
Do not invent shares: missing coverage or a day-volume reset returns None.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from operator import itemgetter


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


def _cum_at_or_before(ordered: list[tuple[float, int]], ts: float) -> int | None:
    i = bisect_right(ordered, ts, key=itemgetter(0)) - 1
    return int(ordered[i][1]) if i >= 0 else None


def window_edges(now: float, spike_sec: float, baseline_sec: float) -> tuple[float, float, float]:
    """The three times the spike reads a cumulative volume at: now, the spike's
    start, and the baseline's start."""
    spike_start = now - float(spike_sec)
    return now, spike_start, spike_start - float(baseline_sec)


def measure_spike(
    samples: list[tuple[float, int]],
    now: float,
    *,
    spike_sec: float,
    baseline_sec: float,
    min_spike_shares: int,
    min_baseline_shares: int,
) -> SpikeMetrics | None:
    """Shares in the spike window vs the prior baseline window, from a list of
    samples (tests, replays). The live engine reads the edges from its ordered
    series and calls ``spike_from_edges`` directly -- no copy, no sort (#619).
    """
    if not samples:
        return None
    ordered = sorted(samples, key=itemgetter(0))
    end, spike_start, base_start = window_edges(now, spike_sec, baseline_sec)
    return spike_from_edges(
        _cum_at_or_before(ordered, end),
        _cum_at_or_before(ordered, spike_start),
        _cum_at_or_before(ordered, base_start),
        spike_sec=spike_sec,
        baseline_sec=baseline_sec,
        min_spike_shares=min_spike_shares,
        min_baseline_shares=min_baseline_shares,
    )


def spike_from_edges(
    cum_end: int | None,
    cum_spike: int | None,
    cum_base: int | None,
    *,
    spike_sec: float,
    baseline_sec: float,
    min_spike_shares: int,
    min_baseline_shares: int,
) -> SpikeMetrics | None:
    """Shares in the spike window vs the prior baseline window, from the
    cumulative day volume at each window edge (``window_edges``).

    Requires a cum-vol sample at or before each window edge. A drop in
    cumulative day volume is a session reset -- not a spike.
    """
    if spike_sec <= 0 or baseline_sec <= 0:
        return None
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
