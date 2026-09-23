"""``tools/perf_report.py`` (ADR 026): a day file in, where the time went out.

Lives with the backend tests because the tool reads the backend's own sample
helpers; the backend job runs it on every PR.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from perf import sample

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "perf_report.py"
_spec = importlib.util.spec_from_file_location("perf_report", _TOOL)
perf_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(perf_report)

_ET = ZoneInfo("America/New_York")


def _ts(hh, mm, ss=0):
    return datetime(2026, 9, 24, hh, mm, ss, tzinfo=_ET).timestamp()


def _sample_line(ts, *, cpu, ib_delay, ops, dropped=0):
    s = sample.build(
        ts=ts, interval_sec=5.0, process_cpu_pct=cpu, threads=12,
        loops={"ib": {"cpu_pct": cpu - 10, "delay_max_ms": ib_delay, "stalled": ib_delay > 200},
               "http": {"cpu_pct": 5.0, "delay_max_ms": 4.0, "stalled": False}},
        ops=ops, gauges={"tape.viewer_dropped": dropped}, gc_collections=(3, 1, 0), gc_pause_ms=2.0,
        gc_max_pause_ms=1.0,
    )
    return {"kind": "sample", **s}


def _day(tmp_path: Path) -> Path:
    lines = [
        _sample_line(_ts(9, 29, 50), cpu=30, ib_delay=20, ops={"ib.l1": {"calls": 500, "busy_ms": 100.0}}),
        _sample_line(_ts(9, 30, 5), cpu=92, ib_delay=640,
                     ops={"ib.l1": {"calls": 4000, "busy_ms": 3000.0},
                          "volume_boost.observe": {"calls": 4000, "busy_ms": 2000.0}}, dropped=120),
        {"kind": "stall", "schema_version": 1, "ts": _ts(9, 30, 2), "id": "1-ib", "loop": "ib",
         "started_ts": _ts(9, 30, 2), "duration_ms": 640.0, "samples": 64,
         "top_frame": "backend/volume_boost_detect.py:59 measure_spike"},
        {"kind": "client", "schema_version": 1, "ts": _ts(9, 30, 5), "window_id": "trader-1", "role": "popout",
         "interval_sec": 5.0, "frames": {"count": 300, "slow": 60, "p95_ms": 48.0},
         "long_frames": {"count": 9, "blocking_ms": 900.0, "max_ms": 220.0,
                         "top": [{"source": "DepthLadder @ index.js", "invoker": "WebSocket.onmessage", "ms": 220.0}]},
         "sockets": {"depth": {"messages": 2000, "bytes": 1}}, "renders": {"StockViewPage": 1500}, "heap_mb": 200.0},
        {"kind": "client", "schema_version": 1, "ts": _ts(9, 30, 5), "window_id": "electron-main",
         "role": "electron", "interval_sec": 5.0,
         "processes": [{"type": "Tab", "window_id": "trader-1", "pid": 7, "cpu_pct": 88.0, "working_set_mb": 500}]},
        {"kind": "sample", "schema_version": 99, "ts": _ts(9, 31)},
        "not json",
    ]
    path = tmp_path / "2026-09-24.jsonl"
    path.write_text("\n".join(x if isinstance(x, str) else json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    stalls = tmp_path / "stalls"
    stalls.mkdir()
    (stalls / "1-ib.json").write_text(json.dumps({"stacks": [{"count": 60, "frames": [
        "backend/ibkr/ticks_handler.py:230 on_ticker_update",
        "backend/volume_boost_detect.py:59 measure_spike"]}]}), encoding="utf-8")
    return tmp_path


def test_read_lines_skips_unknown_versions_and_garbage(tmp_path):
    lines, skipped = perf_report.read_lines(_day(tmp_path) / "2026-09-24.jsonl")
    assert skipped == 2
    assert {ln["kind"] for ln in lines} == {"sample", "stall", "client"}


def test_analyze_names_the_worst_minute_handlers_stalls_and_windows(tmp_path):
    root = _day(tmp_path)
    lines, _ = perf_report.read_lines(root / "2026-09-24.jsonl")
    report = perf_report.analyze(
        lines, stall_reader=lambda sid: json.loads((root / "stalls" / f"{sid}.json").read_text()))
    assert report["worst_minutes"][0]["minute"] == _ts(9, 30) and report["worst_minutes"][0]["stalled"]
    assert [r["op"] for r in report["busiest"]][:2] == ["ib.l1", "volume_boost.observe"]
    worst = report["stalls"]["worst"][0]
    assert worst["top_frame"] == "backend/volume_boost_detect.py:59 measure_spike"
    assert worst["stack"][-1] == "backend/volume_boost_detect.py:59 measure_spike"
    assert report["drops"] == {"tape.viewer_dropped": 120}
    w = report["windows"]["trader-1"]
    assert w["slow_share"] == 0.2 and w["scripts"][0]["script"] == "DepthLadder @ index.js <- WebSocket.onmessage"
    assert w["sockets_per_sec"] == {"depth": 400.0}
    assert "electron-main" not in report["windows"]
    assert report["processes"][0]["window"] == "trader-1" and report["processes"][0]["cpu_mean"] == 88.0
    text = perf_report.render(report, "t")
    assert "volume_boost.observe" in text and "trader-1 (popout): slow frames 20.0%" in text


def test_time_window_filters(tmp_path):
    lines, _ = perf_report.read_lines(_day(tmp_path) / "2026-09-24.jsonl")
    early = perf_report.analyze(lines, end=_ts(9, 30))
    assert early["samples"] == 1 and early["stalls"]["count"] == 0 and not early["windows"]


def test_main_reads_a_folder_and_prints(tmp_path, capsys):
    root = _day(tmp_path)
    assert perf_report.main(["--dir", str(root), "--date", "2026-09-24", "--from", "09:25", "--to", "09:45"]) == 0
    out = capsys.readouterr().out
    assert "Stalls: 1 (ib 1, http 0)" in out and "2 line(s) skipped" in out
    assert perf_report.main(["--dir", str(root), "--date", "2026-09-25"]) == 1
