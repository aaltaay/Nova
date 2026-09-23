"""Performance recorder (ADR 026): the pure parts -- samples, stacks, diagnostics rows."""
from __future__ import annotations

import os

from constants_perf import PERF_DIAG_CPU_FAIL_PCT, PERF_DIAG_CPU_WARN_PCT, PERF_SCHEMA_VERSION
from diagnostics import collect_perf
from perf import sample, stacks


def _sample(ts, *, cpu=10.0, ib_cpu=5.0, delay=3.0, ops=None, gauges=None, stalled=False):
    return sample.build(
        ts=ts, interval_sec=1.0, process_cpu_pct=cpu, threads=9,
        loops={"ib": {"cpu_pct": ib_cpu, "delay_max_ms": delay, "stalled": stalled},
               "http": {"cpu_pct": 2.0, "delay_max_ms": 1.0, "stalled": False}},
        ops=ops or {}, gauges=gauges or {}, gc_collections=(1, 0, 0), gc_pause_ms=0.5, gc_max_pause_ms=0.5,
    )


def test_ops_delta_counts_only_what_ran_and_survives_a_reset():
    prev = {"ib.l1": (10, 5_000_000), "idle": (3, 1_000)}
    now = {"ib.l1": (15, 7_500_000), "idle": (3, 1_000), "new": (2, 1_000_000)}
    assert sample.ops_delta(prev, now) == {
        "ib.l1": {"calls": 5, "busy_ms": 2.5},
        "new": {"calls": 2, "busy_ms": 1.0},
    }
    # Totals went backwards (a reset): count from zero, never negative.
    assert sample.ops_delta({"ib.l1": (100, 9_000_000)}, {"ib.l1": (4, 2_000_000)}) == {
        "ib.l1": {"calls": 4, "busy_ms": 2.0},
    }


def test_build_has_the_documented_shape():
    s = _sample(1000.0)
    assert s["schema_version"] == PERF_SCHEMA_VERSION
    assert set(s) == {"schema_version", "ts", "interval_sec", "process", "loops", "ops", "gauges", "gc"}
    assert set(s["loops"]) == {"ib", "http"}
    assert s["gc"] == {"collections": [1, 0, 0], "pause_ms": 0.5, "max_pause_ms": 0.5}
    missing = sample.build(ts=1.0, interval_sec=1.0, process_cpu_pct=None, threads=1, loops={}, ops={},
                           gauges={}, gc_collections=(0, 0, 0), gc_pause_ms=0, gc_max_pause_ms=0)
    assert missing["loops"]["ib"] == {"cpu_pct": None, "delay_max_ms": None, "stalled": False}


def test_aggregate_sums_ops_averages_cpu_maxes_delay_keeps_last_gauges():
    samples = [
        _sample(1.0, cpu=10, delay=5, ops={"a": {"calls": 2, "busy_ms": 1.0}}, gauges={"q": 1}),
        _sample(2.0, cpu=30, delay=50, ops={"a": {"calls": 3, "busy_ms": 2.0}}, gauges={"q": 7}, stalled=True),
    ]
    agg = sample.aggregate(samples)
    assert agg["ts"] == 2.0 and agg["interval_sec"] == 2.0
    assert agg["process"]["cpu_pct"] == 20.0
    assert agg["loops"]["ib"] == {"cpu_pct": 5.0, "delay_max_ms": 50, "stalled": True}
    assert agg["ops"] == {"a": {"calls": 5, "busy_ms": 3.0}}
    assert agg["gauges"] == {"q": 7}
    assert agg["gc"]["collections"] == [2, 0, 0]
    assert sample.aggregate([]) is None


def test_drop_increase_reports_growth_including_a_counter_seen_first_time():
    first = _sample(1.0, gauges={"archive.dropped": 4, "archive.pending": 9})
    last = _sample(2.0, gauges={"archive.dropped": 10, "archive.pending": 1, "tape.viewer_dropped": 3})
    assert sample.drop_increase([first, last]) == {"archive.dropped": 6, "tape.viewer_dropped": 3}
    assert sample.drop_increase([last]) == {}


def test_busiest_ranks_by_busy_time_per_second():
    samples = [
        _sample(1.0, ops={"a": {"calls": 100, "busy_ms": 10.0}, "b": {"calls": 1, "busy_ms": 40.0}}),
        _sample(2.0, ops={"a": {"calls": 100, "busy_ms": 10.0}}),
    ]
    top = sample.busiest(samples, 5)
    assert [r["op"] for r in top] == ["b", "a"]
    assert top[0]["busy_ms_per_sec"] == 20.0
    assert top[1] == {"op": "a", "busy_ms_per_sec": 10.0, "calls_per_sec": 100.0, "us_per_call": 100.0}


def test_fold_counts_stacks_and_names_the_innermost_repo_frame(tmp_path):
    root = str(tmp_path)
    nova = os.path.join(root, "backend", "volume_boost_detect.py")
    lib = os.path.join(root, ".venv", "Lib", "site-packages", "x.py")
    outside = os.path.join(os.path.dirname(root), "python", "asyncio", "base_events.py")
    hot = ((outside, 10, "run_once"), (nova, 59, "measure_spike"), (lib, 3, "helper"))
    cold = ((outside, 10, "run_once"), (nova, 70, "other"))
    folded, top = stacks.fold([hot, hot, hot, cold], top=12, repo_root=root)
    assert top == "backend/volume_boost_detect.py:59 measure_spike"
    assert folded[0]["count"] == 3
    assert folded[0]["frames"][1] == "backend/volume_boost_detect.py:59 measure_spike"
    assert folded[1]["count"] == 1
    assert stacks.fold([((outside, 1, "f"),)], top=12, repo_root=root)[1] is None


def test_the_recorder_own_gc_hook_never_names_a_stall():
    gc_hook = (stacks.__file__.replace("stacks.py", "gc_watch.py"), 20, "_on_gc")
    caller = (os.path.join(stacks.REPO_ROOT, "backend", "ibkr", "l1_apply.py"), 203, "apply_l1_quote")
    folded, top = stacks.fold([(caller, gc_hook)] * 3, top=12)
    assert top == "backend/ibkr/l1_apply.py:203 apply_l1_quote"
    assert folded[0]["frames"][-1] == "backend/perf/gc_watch.py:20 _on_gc"


def test_capture_is_outermost_first_and_bounded():
    import sys

    def inner():
        return stacks.capture(sys._getframe(), 2)

    captured = inner()
    assert len(captured) == 2
    assert captured[-1][2] == "inner"


def _rows(**kw):
    base = dict(running=True, window=[_sample(100.0), _sample(101.0)], drop_window=[_sample(50.0), _sample(101.0)],
                stalls=[], clients={}, now=101.0, window_sec=60, drop_window_sec=600)
    base.update(kw)
    return {r["id"]: r for r in collect_perf.perf_rows(**base)}


def test_rows_off_and_waiting():
    off = collect_perf.perf_rows(running=False, window=[], drop_window=[], stalls=[], clients={}, now=1.0,
                                 window_sec=60, drop_window_sec=600)
    assert [(r["id"], r["state"]) for r in off] == [("perf_recorder", "off")]
    waiting = collect_perf.perf_rows(running=True, window=[], drop_window=[], stalls=[], clients={}, now=1.0,
                                     window_sec=60, drop_window_sec=600)
    assert [(r["id"], r["state"]) for r in waiting] == [("perf_recorder", "unknown")]


def test_rows_group_and_cpu_thresholds():
    rows = _rows()
    assert set(rows) == {"perf_process_cpu", "perf_ib_loop", "perf_http_loop", "perf_stalls",
                         "perf_queues", "perf_windows", "perf_handlers"}
    assert all(r["group"] == "performance" for r in rows.values())
    assert rows["perf_process_cpu"]["state"] == "ok"
    warm = _rows(window=[_sample(100.0, cpu=PERF_DIAG_CPU_WARN_PCT, ib_cpu=PERF_DIAG_CPU_FAIL_PCT)])
    assert warm["perf_process_cpu"]["state"] == "warn"
    assert warm["perf_ib_loop"]["state"] == "fail"
    assert "longest callback wait 3 ms" in warm["perf_ib_loop"]["detail"]


def test_stall_row_names_the_line():
    stall = {"id": "1-ib", "loop": "ib", "started_ts": 90.0, "duration_ms": 640.0,
             "top_frame": "backend/volume_boost_detect.py:59 measure_spike"}
    rows = _rows(stalls=[stall])
    assert rows["perf_stalls"]["state"] == "warn"
    assert "640 ms on the ib loop at backend/volume_boost_detect.py:59" in rows["perf_stalls"]["detail"]
    old = dict(stall, started_ts=101.0 - 7200)
    assert _rows(stalls=[old])["perf_stalls"]["state"] == "ok"


def test_queue_row_warns_on_drops():
    rows = _rows(drop_window=[_sample(1.0, gauges={"tape.viewer_dropped": 0}),
                              _sample(101.0, gauges={"tape.viewer_dropped": 120})])
    assert rows["perf_queues"]["state"] == "warn"
    assert "tape.viewer_dropped +120" in rows["perf_queues"]["detail"]


def test_window_row_uses_fresh_reports_and_worst_share():
    def report(slow, count=100, received=100.0, role="main"):
        return {"role": role, "visible": True, "received_ts": received, "frames": {"count": count, "slow": slow},
                "long_frames": {"count": 3, "blocking_ms": 120.0, "top": []}}

    assert _rows()["perf_windows"]["state"] == "unknown"
    ok = _rows(clients={"main": report(1)})
    assert ok["perf_windows"]["state"] == "ok"
    bad = _rows(clients={"main": report(1), "trader-1": report(30, role="popout"),
                         "stale": report(90, received=1.0),
                         "electron-main": {"role": "electron", "received_ts": 100.0, "processes": [{"pid": 1}]}})
    assert bad["perf_windows"]["state"] == "fail"
    assert "worst trader-1: 30%" in bad["perf_windows"]["detail"]
    assert "stale" not in bad["perf_windows"]["evidence"]["windows"]
    assert bad["perf_windows"]["evidence"]["processes"] == [{"pid": 1}]
