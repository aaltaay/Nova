"""Performance recorder (ADR 026): the recorder, the files, the routes and the gauges."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import constants_perf as cp
from metrics import op_metrics
from perf import counters, gauges, recorder, stall_watch
from perf.routes import router
from perf.store import PerfStore, et_date

_ET = ZoneInfo("America/New_York")


@pytest.fixture(autouse=True)
def _reset():
    recorder.reset_for_tests()
    stall_watch.reset_for_tests()
    counters.reset_for_tests()
    op_metrics.reset_for_tests()
    yield
    recorder.reset_for_tests()
    stall_watch.reset_for_tests()
    op_metrics.reset_for_tests()


@pytest.fixture
def store(tmp_path):
    s = PerfStore(tmp_path / "perf")
    recorder.configure(s)
    return s


def _lines(store: PerfStore) -> list[dict]:
    store.drain()
    out = []
    for path in sorted(store.root.glob("*.jsonl")):
        out += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return out


def _ts(hh: int, mm: int, ss: int = 0) -> float:
    return datetime(2026, 9, 24, hh, mm, ss, tzinfo=_ET).timestamp()


def test_tick_builds_a_sample_and_persists_one_aggregate_per_five(store):
    op_metrics.record("ib.l1", 2_000_000)
    base = _ts(9, 30)
    for i in range(cp.PERF_PERSIST_EVERY_SEC):
        s = recorder.tick(now=base + i)
    assert set(s["gauges"]) >= {"archive.pending", "tape.viewer_dropped", "depth.viewer_dropped"}
    lines = _lines(store)
    assert [ln["kind"] for ln in lines] == ["sample"]
    assert lines[0]["schema_version"] == cp.PERF_SCHEMA_VERSION
    assert lines[0]["ops"]["ib.l1"] == {"calls": 1, "busy_ms": 2.0}
    assert (store.root / "2026-09-24.jsonl").is_file()
    assert len(recorder.samples(60, now=base + 5)) == cp.PERF_PERSIST_EVERY_SEC


def test_a_finished_stall_gets_context_then_a_file(store):
    base = _ts(9, 30)
    for i in range(3):
        recorder.tick(now=base + i)
    stall_watch.completed.put({
        "id": f"{int((base + 2.5) * 1000)}-ib", "loop": "ib", "started_ts": base + 2.5, "ended_ts": base + 3.2,
        "duration_ms": 700.0, "samples": 70, "truncated": False, "top_frame": "backend/x.py:1 f",
        "stacks": [{"count": 70, "frames": ["backend/x.py:1 f"]}],
    })
    recorder.tick(now=base + 4)
    summary = recorder.stall_summaries()[0]
    assert summary["file"] is None and "stacks" not in summary
    report = recorder.stall_report(summary["id"])
    assert len(report["before"]) == 3 and "after" not in report
    for i in range(5, 5 + cp.PERF_STALL_CONTEXT_SEC):
        recorder.tick(now=base + i)
    assert recorder.stall_summaries()[0]["file"] is not None
    store.drain()
    on_disk = json.loads(store.stall_path(summary["id"]).read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == cp.PERF_SCHEMA_VERSION
    assert on_disk["stacks"][0]["count"] == 70 and len(on_disk["after"]) > 0
    kinds = [ln["kind"] for ln in _lines(store)]
    assert "stall" in kinds


def test_stall_files_are_budgeted_per_hour(store, monkeypatch):
    monkeypatch.setattr("perf.store.PERF_STALL_FILES_PER_HOUR", 2)
    assert store.put_stall({"id": "1-ib"}) and store.put_stall({"id": "2-ib"})
    assert store.put_stall({"id": "3-ib"}) is False
    assert store.stall_files_skipped == 1


def test_day_file_cap_stops_samples_but_keeps_stalls(store, monkeypatch):
    monkeypatch.setattr("perf.store.PERF_DAY_FILE_MAX_MB", 0)
    ts = _ts(10, 0)
    store.put({"kind": "sample", "ts": ts, "schema_version": 1})
    store.drain()
    store.put({"kind": "sample", "ts": ts + 1, "schema_version": 1})
    store.put({"kind": "client", "ts": ts + 1, "schema_version": 1})
    store.put({"kind": "stall", "ts": ts + 1, "schema_version": 1})
    assert [ln["kind"] for ln in _lines(store)] == ["sample", "stall"]


def test_retention_removes_old_days_and_old_stall_reports(store):
    store.root.mkdir(parents=True)
    store.stalls_dir.mkdir()
    now = _ts(12, 0)
    old_day = et_date(now - (cp.PERF_RETENTION_DAYS + 1) * 86400)
    keep_day = et_date(now - 86400)
    (store.root / f"{old_day}.jsonl").write_text("{}\n")
    (store.root / f"{keep_day}.jsonl").write_text("{}\n")
    old_stall = store.stall_path("1-ib")
    old_stall.write_text("{}")
    os.utime(old_stall, (now - (cp.PERF_RETENTION_DAYS + 1) * 86400,) * 2)
    assert store.sweep(now=now) == 2
    assert [p.stem for p in store.root.glob("*.jsonl")] == [keep_day]


def test_writer_thread_writes_off_the_caller(store):
    store.start()
    writer = store._thread
    try:
        store.put({"kind": "sample", "ts": _ts(9, 31), "schema_version": 1})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not list(store.root.glob("*.jsonl")):
            time.sleep(0.05)
    finally:
        store.stop()
    assert list(store.root.glob("*.jsonl"))
    assert writer is not None and writer.name == "nova-perf-writer" and not writer.is_alive()


def test_a_full_queue_counts_drops(store, monkeypatch):
    for _ in range(cp.PERF_WRITE_QUEUE_MAX + 3):
        store.put({"kind": "sample", "ts": 1.0})
    assert store.write_dropped == 3


def test_every_gauge_probe_answers():
    """Pins the owner state each probe reads -- a rename breaks here, not silently."""
    for name, probe in gauges.PROBES:
        values = probe()
        assert values and all(isinstance(v, (int, float)) for v in values.values()), name
    counters.incr("tape.viewer_dropped", 4)
    assert gauges.read()["tape.viewer_dropped"] == 4


# -- routes --------------------------------------------------------------

@pytest.fixture
def client(store):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _report(**over):
    body = {
        "schema_version": 1, "window_id": "trader-1", "role": "popout", "visible": True, "interval_sec": 5.0,
        "ui_tag": "v612", "frames": {"count": 300, "slow": 12, "p95_ms": 21.5},
        "long_frames": {"count": 4, "blocking_ms": 180.0, "max_ms": 95.0,
                        "top": [{"source": "DepthLadder @ index.js", "invoker": "WebSocket.onmessage", "ms": 95.0}]},
        "sockets": {"depth": {"messages": 400, "bytes": 90000}}, "renders": {"StockViewPage": 410},
        "heap_mb": 180.2, "dom_nodes": 5400, "processes": None,
    }
    body.update(over)
    return body


def test_client_report_is_kept_and_written(client, store):
    assert client.post("/api/perf/client", json=_report()).json() == {"ok": True}
    live = client.get("/api/perf/live").json()
    kept = live["clients"]["trader-1"]
    assert kept["frames"]["slow"] == 12 and "received_ts" in kept
    assert [ln["kind"] for ln in _lines(store)] == ["client"]


@pytest.mark.parametrize("bad", [
    {"schema_version": 2},
    {"window_id": "bad id!"},
    {"role": "tab"},
    {"sockets": {f"s{i}": {"messages": 1, "bytes": 1} for i in range(cp.PERF_CLIENT_MAX_KEYS + 1)}},
    {"long_frames": {"count": 1, "blocking_ms": 1, "max_ms": 1, "top": [{"source": "x", "ms": 1}] * 4}},
])
def test_client_report_is_validated(client, bad):
    assert client.post("/api/perf/client", json=_report(**bad)).status_code == 422
    assert client.get("/api/perf/live").json()["clients"] == {}


def test_oversized_client_report_is_refused(client):
    body = json.dumps(_report(ui_tag=None)) + " " * cp.PERF_CLIENT_MAX_BODY_BYTES
    resp = client.post("/api/perf/client", content=body, headers={"content-type": "application/json"})
    assert resp.status_code == 413


def test_electron_report_carries_processes(client):
    report = _report(window_id="electron-main", role="electron", visible=None, frames=None, long_frames=None,
                     processes=[{"type": "Tab", "window_id": "main", "pid": 42, "cpu_pct": 31.5,
                                 "working_set_mb": 410.0}])
    assert client.post("/api/perf/client", json=report).status_code == 200


def test_live_and_stalls_routes(client):
    recorder.tick(now=time.time())
    live = client.get("/api/perf/live?seconds=60").json()
    assert live["schema_version"] == 1 and live["recorder"]["running"] is True
    assert len(live["samples"]) == 1
    assert client.get("/api/perf/stalls").json() == {"schema_version": 1, "stalls": []}
    assert client.get("/api/perf/stalls/1726000000000-ib").status_code == 404
    assert client.get("/api/perf/stalls/..%2Fsecret").status_code == 404



def test_a_stall_report_on_disk_is_served_by_id(client, store):
    store.stalls_dir.mkdir(parents=True)
    store.stall_path("1790000000000-ib").write_text(json.dumps({"id": "1790000000000-ib", "stacks": []}))
    assert client.get("/api/perf/stalls/1790000000000-ib").json()["id"] == "1790000000000-ib"
    assert client.get("/api/perf/stalls/1790000000001-ib").status_code == 404

# -- runtime ---------------------------------------------------------------

def test_runtime_starts_and_stops_its_threads(monkeypatch, tmp_path):
    import asyncio

    from perf import runtime

    monkeypatch.setenv("NOVA_PERF", "1")
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))

    async def run() -> list[str]:
        tasks = runtime.start()
        names = sorted(t.name for t in threading.enumerate() if t.name.startswith("nova-perf-"))
        runtime.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        return names

    assert asyncio.run(run()) == ["nova-perf-watch", "nova-perf-writer"]
    assert not [t for t in threading.enumerate() if t.name.startswith("nova-perf-") and t.is_alive()]
    assert recorder.status()["dir"] == str(tmp_path / "perf")


def test_runtime_off_switch(monkeypatch):
    import asyncio

    from perf import runtime

    monkeypatch.setenv("NOVA_PERF", "0")
    assert asyncio.run(_start_off(runtime)) == []
    assert recorder.status()["running"] is False


async def _start_off(runtime):
    return runtime.start()
