"""CPU share of each event-loop thread and of the whole process (ADR 026).

``time.thread_time_ns()`` is the CPU time of the calling thread, so a
coroutine running on a loop reads that loop's own thread. The delta over wall
time is the share of one core the loop used. Windows' thread clock ticks at
about 15.6 ms, so a one-second reading is good to about +/-2%.
"""
from __future__ import annotations

import asyncio
import threading
import time

from constants_perf import PERF_SAMPLE_INTERVAL_SEC


# loop name -> last full-interval CPU percent (None until one interval ran).
_cpu_pct: dict[str, float | None] = {}
_process_prev: tuple[int, int] | None = None  # (process_time_ns, perf_counter_ns)


def cpu_pct(interval_cpu_ns: int, interval_wall_ns: int) -> float | None:
    """CPU time over wall time, in percent of one core. Pure."""
    if interval_wall_ns <= 0 or interval_cpu_ns < 0:
        return None
    return round(100.0 * interval_cpu_ns / interval_wall_ns, 1)


def loop_cpu_pct(name: str) -> float | None:
    return _cpu_pct.get(name)


def process_reading() -> tuple[float | None, int]:
    """Process CPU percent since the previous call, and the live thread count."""
    global _process_prev
    now = (time.process_time_ns(), time.perf_counter_ns())
    prev, _process_prev = _process_prev, now
    threads = threading.active_count()
    if prev is None:
        return None, threads
    return cpu_pct(now[0] - prev[0], now[1] - prev[1]), threads


async def sample_loop(name: str) -> None:
    """Run on the loop being measured; publishes its CPU share every interval."""
    _cpu_pct.setdefault(name, None)
    cpu_prev = time.thread_time_ns()
    wall_prev = time.perf_counter_ns()
    while True:
        await asyncio.sleep(PERF_SAMPLE_INTERVAL_SEC)
        cpu_now = time.thread_time_ns()
        wall_now = time.perf_counter_ns()
        _cpu_pct[name] = cpu_pct(cpu_now - cpu_prev, wall_now - wall_prev)
        cpu_prev, wall_prev = cpu_now, wall_now


def reset_for_tests() -> None:
    global _process_prev
    _cpu_pct.clear()
    _process_prev = None
