"""Bounded, process-local operation latency measurements."""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from functools import wraps
from typing import AsyncIterator, Iterator

from constants_metrics import OP_METRICS_RING_SIZE


@dataclass
class _OpState:
    durations_ns: deque[int] = field(
        default_factory=lambda: deque(maxlen=OP_METRICS_RING_SIZE)
    )
    count: int = 0
    error_count: int = 0
    last_sample_ns: int | None = None


_lock = threading.Lock()
_operations: dict[str, _OpState] = {}


def _percentile(values: list[int], percentile: int) -> float | None:
    """Return nearest-rank percentile in milliseconds."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil((percentile / 100) * len(ordered)))
    return ordered[rank - 1] / 1_000_000


def record(op_name: str, duration_ns: int, ok: bool = True) -> None:
    """Record one duration without persistence or external I/O."""
    name = str(op_name).strip()
    if not name:
        raise ValueError("op_name must not be empty")
    duration = int(duration_ns)
    if duration < 0:
        raise ValueError("duration_ns must be non-negative")
    observed_ns = time.perf_counter_ns()
    with _lock:
        state = _operations.setdefault(name, _OpState())
        state.durations_ns.append(duration)
        state.count += 1
        if not ok:
            state.error_count += 1
        state.last_sample_ns = observed_ns


def record_since(op_name: str, started_ns: int, ok: bool = True) -> None:
    """Record elapsed monotonic time from a previously captured start."""
    record(op_name, time.perf_counter_ns() - int(started_ns), ok=ok)


def snapshot() -> dict:
    """Return bounded percentile rollups for every recorded operation."""
    now_ns = time.perf_counter_ns()
    with _lock:
        copied = {
            name: (
                list(state.durations_ns),
                state.count,
                state.error_count,
                state.last_sample_ns,
            )
            for name, state in _operations.items()
        }

    operations: dict[str, dict] = {}
    for name, (durations, count, error_count, last_sample_ns) in sorted(copied.items()):
        age_ms = (
            max(0, now_ns - last_sample_ns) / 1_000_000
            if last_sample_ns is not None
            else None
        )
        operations[name] = {
            "count": count,
            "error_count": error_count,
            "sample_count": len(durations),
            "p50_ms": _percentile(durations, 50),
            "p95_ms": _percentile(durations, 95),
            "p99_ms": _percentile(durations, 99),
            "max_ms": max(durations) / 1_000_000 if durations else None,
            "last_sample_age_ms": age_ms,
        }
    return {
        "clock": "perf_counter_ns",
        "ring_size": OP_METRICS_RING_SIZE,
        "operations": operations,
    }


@asynccontextmanager
async def timed(op_name: str) -> AsyncIterator[None]:
    """Time an async operation and preserve its original exception."""
    started_ns = time.perf_counter_ns()
    try:
        yield
    except BaseException:
        record(op_name, time.perf_counter_ns() - started_ns, ok=False)
        raise
    else:
        record(op_name, time.perf_counter_ns() - started_ns, ok=True)


@contextmanager
def timed_sync(op_name: str) -> Iterator[None]:
    """Time a synchronous operation and preserve its original exception."""
    started_ns = time.perf_counter_ns()
    try:
        yield
    except BaseException:
        record_since(op_name, started_ns, ok=False)
        raise
    else:
        record_since(op_name, started_ns, ok=True)


def timed_async(op_name: str):
    """Decorate an async operation while preserving its call contract."""
    def decorate(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with timed(op_name):
                return await func(*args, **kwargs)
        return wrapper
    return decorate


def reset_for_tests() -> None:
    with _lock:
        _operations.clear()
