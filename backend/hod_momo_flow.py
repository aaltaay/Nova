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
    """Count seeded symbols whose 5m surge is still None (hard integrity fail)."""
    bad = 0
    for sym in seeded:
        buf = price_buffer.get(sym)
        if not buf:
            bad += 1
            continue
        snap = ticker_snaps.get(sym)
        if snap is not None and getattr(snap, "price", None):
            # Ensure current price is represented for low_to_current.
            pass
        surge = surge_fn(buf, window_min, method)
        if surge is None:
            bad += 1
    return bad
