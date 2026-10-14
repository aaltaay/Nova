"""Isolated HOD/Volume boost burst comparison for #619, no broker or operator files.

Run each history in a fresh process, for example:
    py -3 backend/tests/bench_hod_burst.py --history reference
    py -3 backend/tests/bench_hod_burst.py --history indexed
Optional --profile attributes Python work; --trace measures retained allocations.
Those instrumented runs are separate from the native duration comparison.
"""
from __future__ import annotations

import argparse
import cProfile
import gc
import io
import json
import logging
import pstats
import subprocess
import sys
import time
import tracemalloc
from collections import deque
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# This is the same pre-import operator isolation used by the backend suite.
from tests.conftest import reset_hod_engine_state
import hod_momo as hm
import hod_momo_market as hod_market
import hod_momo_metrics as metrics
import hod_momo_decision_journal as journal
import hod_momo_trade_log as trade_log
import market
import volume_boost
from hod_momo_models import TickerSnap
from hod_prices import PriceHistory
from perf import gc_watch
from perf.heap import process_memory


def reference_update(symbol, price, ts):
    """The prior live ordered-deque write, paired with the unchanged scan reference."""
    buf = hm.get_state().price_buffer.setdefault(symbol, deque())
    later = []
    while buf and buf[-1][0] > ts:
        later.append(buf.pop())
    buf.append((ts, price))
    buf.extend(reversed(later))
    while buf and buf[0][0] < ts - 3600:
        buf.popleft()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", choices=("reference", "indexed"), required=True)
    parser.add_argument("--ticks", type=int, default=20_000)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    if args.ticks <= 0:
        parser.error("--ticks must be positive")
    # Exclude writer I/O in both cases, preserve caller-side enabled log formatting.
    for module, log in ((journal, journal.journal_log), (trade_log, trade_log.trade_log)):
        module._listener.stop()
        log.handlers[:] = [logging.NullHandler()]
    journal.journal_log.setLevel(logging.INFO)
    trade_log.trade_log.setLevel(logging.DEBUG)
    at_open = datetime(2026, 10, 14, 9, 30, tzinfo=market.ET)
    market.now_et = lambda: at_open
    stamp = at_open.timestamp()
    # Warm the actual engine's lazy imports before constructing the measured heap.
    reset_hod_engine_state()
    hm.on_trade_update("WARM", 10, stamp, volume=100_000, day_high=10)
    volume_boost.observe_l1("WARM", 100_000, 10, stamp)
    reset_hod_engine_state()
    volume_boost.reset_for_tests()
    state = hm.get_state()
    state.master.min_price = state.master.min_volume = state.master.min_rvol = 0
    state.master.premarket_min_rvol = state.master.afterhours_min_rvol = 0
    state.master.hod_required = False
    for config in state.configs.values():
        config.enabled = config.strategy_id in (10, 11, 12)
        config.requires_hod = False
        config.min_rvol = 0
    if args.trace:
        tracemalloc.start()
    for sym in ("LOAD0", "LOAD1", "LOAD2", "LOAD3"):
        state.ticker_snaps[sym] = TickerSnap(price=10, volume=1_000_000, avg_volume=1_000_000,
                                           change_pct=20, float_shares=1_000_000)
        state.session_highs[sym] = 12
        state.session_high_seeded.add(sym)
        state.session_high_source[sym] = "bars"
        points = ((stamp - 3600 + i / 10, 10 + i % 71 / 1000) for i in range(36_000))
        state.price_buffer[sym] = PriceHistory(points) if args.history == "indexed" else deque(points)
        for i in range(36_000):
            metrics.update_cum_volume(sym, i * 100, stamp - 3600 + i / 10)
    if args.history == "reference":
        hod_market.update_price_buffer = reference_update
    gc.collect()
    gc.freeze()
    gc_watch.reset_for_tests()
    gc_watch.install()
    before = {"tracked": len(gc.get_objects()), "frozen": gc.get_freeze_count(),
              "private_bytes": process_memory()["private_bytes"]}
    profile = cProfile.Profile() if args.profile else None
    if profile:
        profile.enable()
    started, cpu_started = time.perf_counter(), time.process_time()
    hod_durations, boost_durations, hod_cpu, boost_cpu = [], [], [], []
    for i in range(args.ticks):
        sym, ts = f"LOAD{i % 4}", stamp + i / 500
        began, began_cpu = time.perf_counter_ns(), time.thread_time_ns()
        hm.on_trade_update(sym, 10.08, ts, volume=3_600_000 + i * 100, day_high=12)
        hod_cpu.append(time.thread_time_ns() - began_cpu)
        hod_durations.append(time.perf_counter_ns() - began)
        began, began_cpu = time.perf_counter_ns(), time.thread_time_ns()
        volume_boost.observe_l1(sym, 3_600_000 + i * 100, 10.08, ts)
        boost_cpu.append(time.thread_time_ns() - began_cpu)
        boost_durations.append(time.perf_counter_ns() - began)
    elapsed, cpu_sec = time.perf_counter() - started, time.process_time() - cpu_started
    # Freeze the diagnostic totals at the measured boundary. Constructing the
    # report and reading OS memory may themselves allocate/collect afterward.
    gc_watch.uninstall()
    if profile:
        profile.disable()
    counts, pause_ns = gc_watch.read()
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2],
                              capture_output=True, text=True, check=True).stdout.strip()
    result = {"history": args.history, "ticks": args.ticks, "profile": args.profile, "trace": args.trace,
              "base_revision": revision,
              "workload": {"symbols": 4, "seed_prices_per_symbol": 36_000, "seed_seconds": 3600,
                           "seed_hz_per_symbol": 10, "burst_hz_total": 500,
                           "strategies": [10, 11, 12], "writer_log_sink": "enabled formatting, null output"},
              "elapsed_sec": elapsed, "cpu_sec": cpu_sec, "gc_collections": counts,
              "gc_pause_ms": pause_ns / 1e6, "gc_pause_ms_by_gen": [v / 1e6 for v in gc_watch.read_by_gen()],
              "gc_max_ms": gc_watch.take_max_ms(), "gc_max_ms_by_gen": gc_watch.take_max_ms_by_gen(),
              "thresholds": gc.get_threshold(), "before": before,
              "after": {"tracked": len(gc.get_objects()), "frozen": gc.get_freeze_count(),
                        "private_bytes": process_memory()["private_bytes"]},
              "retained_prices": sum(map(len, state.price_buffer.values())),
              "retained_decisions": len(state.recent_decisions),
              "per_symbol_decisions": {sym: len(rows) for sym, rows in state.per_symbol_decisions.items()}}
    for name, durations, cpu in (("hod", hod_durations, hod_cpu),
                                 ("volume_boost", boost_durations, boost_cpu)):
        durations.sort()
        result[name] = {"mean_ms": sum(durations) / len(durations) / 1e6,
                        "p99_ms": durations[int(len(durations) * .99)] / 1e6,
                        "max_ms": max(durations) / 1e6,
                        "over_200_ms": sum(v > 200_000_000 for v in durations),
                        "thread_cpu_mean_ms": sum(cpu) / len(cpu) / 1e6,
                        "thread_cpu_max_ms": max(cpu) / 1e6}
    result["thread_cpu_limit"] = "Windows per-call thread CPU can be coarse, aggregate means are informative."
    if args.trace:
        result["traced_bytes"], result["traced_peak_bytes"] = tracemalloc.get_traced_memory()
    if profile:
        stream = io.StringIO()
        pstats.Stats(profile, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(20)
        result["attribution"] = stream.getvalue()
    gc_watch.uninstall()
    gc.unfreeze()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
