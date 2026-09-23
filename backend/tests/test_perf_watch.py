"""Performance recorder (ADR 026): the stall catcher, loop CPU, GC pauses, handler timers."""
from __future__ import annotations

import asyncio
import gc
import threading
import time

import pytest

from metrics import op_metrics
from perf import gc_watch, loop_cpu, stall_watch


@pytest.fixture(autouse=True)
def _reset():
    op_metrics.reset_for_tests()
    stall_watch.reset_for_tests()
    loop_cpu.reset_for_tests()
    yield
    stall_watch.reset_for_tests()
    gc_watch.reset_for_tests()
    op_metrics.reset_for_tests()


class _LoopThread:
    """A real event loop on its own thread, like the IB loop."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        while not self.loop.is_running():
            time.sleep(0.005)
        return self

    def __exit__(self, *exc):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        self.loop.close()


def blocking_callback() -> None:
    """Stands in for a synchronous SQLite write on the loop."""
    time.sleep(0.5)


def _wait_report(timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not stall_watch.completed.empty():
            return stall_watch.completed.get_nowait()
        time.sleep(0.02)
    raise AssertionError("no stall report")


def test_a_blocked_loop_yields_one_report_naming_the_blocking_function():
    with _LoopThread() as lt:
        stall_watch.watch("ib", lt.loop)
        stall_watch.start()
        time.sleep(0.2)  # a few healthy pings first
        lt.loop.call_soon_threadsafe(blocking_callback)
        report = _wait_report()
    assert report["loop"] == "ib"
    assert 250 <= report["duration_ms"] <= 1500
    assert report["samples"] >= 5
    assert report["top_frame"] is not None and "blocking_callback" in report["top_frame"]
    assert report["top_frame"].startswith("backend/tests/test_perf_watch.py:")
    assert report["stacks"][0]["frames"][-1].endswith("blocking_callback")
    assert report["id"].endswith("-ib")
    assert stall_watch.completed.empty()


def test_a_healthy_loop_reports_small_delays_and_no_stall():
    with _LoopThread() as lt:
        stall_watch.watch("http", lt.loop)
        stall_watch.start()
        time.sleep(0.4)
        delay, stalled = stall_watch.take_delay("http")
    assert delay is not None and delay < 150
    assert stalled is False
    assert stall_watch.completed.empty()
    assert stall_watch.take_delay("nobody") == (None, False)


def test_take_delay_counts_a_wait_still_in_progress():
    with _LoopThread() as lt:
        stall_watch.watch("ib", lt.loop)
        stall_watch.start()
        time.sleep(0.15)
        lt.loop.call_soon_threadsafe(blocking_callback)
        time.sleep(0.35)
        delay, stalled = stall_watch.take_delay("ib")
        _wait_report()
    assert delay is not None and delay >= 200
    assert stalled is True


def test_cpu_pct_is_cpu_over_wall():
    assert loop_cpu.cpu_pct(250, 1000) == 25.0
    assert loop_cpu.cpu_pct(0, 0) is None
    assert loop_cpu.cpu_pct(-1, 10) is None


def test_sample_loop_measures_its_own_thread(monkeypatch):
    monkeypatch.setattr(loop_cpu, "PERF_SAMPLE_INTERVAL_SEC", 0.5)

    def spin(seconds: float) -> None:
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            pass

    with _LoopThread() as lt:
        lt.loop.call_soon_threadsafe(lambda: lt.loop.create_task(loop_cpu.sample_loop("ib")))
        time.sleep(0.05)
        lt.loop.call_soon_threadsafe(spin, 0.25)
        time.sleep(0.7)
        pct = loop_cpu.loop_cpu_pct("ib")
    assert pct is not None and 20 <= pct <= 90


def test_process_reading_first_call_is_none_then_a_number():
    assert loop_cpu.process_reading()[0] is None
    time.sleep(0.05)
    pct, threads = loop_cpu.process_reading()
    assert pct is not None and pct >= 0
    assert threads >= 1


def test_gc_watch_times_collections():
    gc_watch.reset_for_tests()
    gc_watch.install()
    before, pause_before = gc_watch.read()
    gc.collect()
    after, pause_after = gc_watch.read()
    assert after[2] == before[2] + 1
    assert pause_after > pause_before
    assert gc_watch.take_max_ms() >= 0
    assert gc_watch.take_max_ms() == 0
    gc_watch.uninstall()
    gc.collect()
    assert gc_watch.read()[0] == after


@op_metrics.timed_fn("unit.hot")
def _hot(x: int) -> int:
    if x < 0:
        raise ValueError("negative")
    return x * 2


def test_timed_fn_keeps_the_contract_and_the_totals():
    assert _hot(3) == 6
    with pytest.raises(ValueError):
        _hot(-1)
    snap = op_metrics.snapshot()["operations"]["unit.hot"]
    assert snap["count"] == 2 and snap["error_count"] == 1
    count, total_ns = op_metrics.totals()["unit.hot"]
    assert count == 2 and total_ns > 0
    assert snap["total_ms"] == pytest.approx(total_ns / 1e6)


def test_timed_fn_survives_a_reset():
    _hot(1)
    op_metrics.reset_for_tests()
    assert "unit.hot" not in op_metrics.totals()
    _hot(1)
    assert op_metrics.totals()["unit.hot"][0] == 1


def test_timer_overhead_stays_inside_the_budget():
    """ADR 026: under 1% of IB-loop CPU at 500 ticks/s, about four timed ops a tick.

    That budget is 5 us a call; the assert is loose so a loaded CI box does not
    flake, and the measured figure is printed for the PR.
    """
    def plain(x):
        return x

    timed = op_metrics.timed_fn("unit.overhead")(plain)
    n = 100_000
    t0 = time.perf_counter()
    for i in range(n):
        plain(i)
    t1 = time.perf_counter()
    for i in range(n):
        timed(i)
    t2 = time.perf_counter()
    per_call_us = ((t2 - t1) - (t1 - t0)) / n * 1e6
    print(f"timed_fn overhead: {per_call_us:.2f} us/call")
    assert per_call_us < 25
