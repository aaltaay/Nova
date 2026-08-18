"""Pure HOD Momo flow / buffer-span helpers (no module globals)."""
from __future__ import annotations

from collections import deque
from typing import Any


def buffer_span_sec(buf: deque[tuple[float, float]] | list[tuple[float, float]] | None) -> float:
    if not buf:
        return 0.0
    return max(0.0, float(buf[-1][0]) - float(buf[0][0]))


def count_surge_ready(
    price_buffer: dict[str, deque[tuple[float, float]]],
    min_span_sec: float,
) -> tuple[int, int]:
    """Return (ready_count, buffer_symbol_count)."""
    ready = 0
    for buf in price_buffer.values():
        if buffer_span_sec(buf) >= min_span_sec:
            ready += 1
    return ready, len(price_buffer)


def count_surge_none_after_seed(
    *,
    seeded: set[str],
    price_buffer: dict[str, deque[tuple[float, float]]],
    ticker_snaps: dict[str, Any],
    surge_fn,
    window_min: int = 5,
    method: str = "low_to_current",
) -> int:
    """Count seeded symbols whose surge is None after the window has elapsed.

    A live-only buffer is structurally not-ready until ``window_min`` of
    prints accumulate -- that is warmup, not a Nova defect.
    """
    need_span = max(1, int(window_min)) * 60.0
    bad = 0
    _ = ticker_snaps
    for _sym in seeded:
        buf = price_buffer.get(_sym)
        if buffer_span_sec(buf) < need_span:
            continue
        surge = surge_fn(buf, window_min, method)
        if surge is None:
            bad += 1
    return bad
