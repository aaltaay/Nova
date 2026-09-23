"""The once-a-second performance sample (ADR 026).

Runs as a task on the HTTP loop. Each tick reads every source (loop CPU and
delay, op_metrics totals, gauges, GC), keeps the sample in memory, hands a
5-second aggregate to the store, and turns finished stalls from the watcher
into reports with 30 s of samples either side. Reads never block: the store
only enqueues.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from typing import Any

from constants_perf import (
    PERF_PERSIST_EVERY_SEC,
    PERF_RING_SEC,
    PERF_SAMPLE_INTERVAL_SEC,
    PERF_SCHEMA_VERSION,
    PERF_STALL_CONTEXT_SEC,
    PERF_STALL_RECENT,
)
from metrics import op_metrics
from perf import gauges, gc_watch, loop_cpu, sample, stall_watch
from perf.store import PerfStore

logger = logging.getLogger(__name__)

_REPORT_ONLY = ("stacks", "before", "after")

_lock = threading.Lock()
_ring: deque[dict[str, Any]] = deque(maxlen=int(PERF_RING_SEC / PERF_SAMPLE_INTERVAL_SEC))
_unpersisted: list[dict[str, Any]] = []
_stalls: deque[dict[str, Any]] = deque(maxlen=PERF_STALL_RECENT)
_reports: dict[str, dict[str, Any]] = {}
_awaiting_after: list[dict[str, Any]] = []
_clients: dict[str, dict[str, Any]] = {}
_store: PerfStore | None = None
_since: float | None = None
_prev: dict[str, Any] = {}


def configure(store: PerfStore | None) -> None:
    global _store, _since
    _store = store
    _since = time.time()


def _window(start: float, end: float) -> list[dict[str, Any]]:
    with _lock:
        return [s for s in _ring if start <= s["ts"] <= end]


def _read_loops() -> dict[str, dict[str, Any]]:
    out = {}
    for name in sample.LOOPS:
        delay, stalled = stall_watch.take_delay(name)
        out[name] = {"cpu_pct": loop_cpu.loop_cpu_pct(name), "delay_max_ms": delay, "stalled": stalled}
    return out


def tick(now: float | None = None) -> dict[str, Any]:
    """Take one sample; persist and finish stalls as due. Returns the sample."""
    now = time.time() if now is None else now
    totals = op_metrics.totals()
    gc_counts, gc_pause_ns = gc_watch.read()
    process_cpu, threads = loop_cpu.process_reading()
    prev_ts = _prev.get("ts")
    prev_gc_counts, prev_gc_pause = _prev.get("gc", ((0, 0, 0), 0))
    s = sample.build(
        ts=now,
        interval_sec=(now - prev_ts) if prev_ts else PERF_SAMPLE_INTERVAL_SEC,
        process_cpu_pct=process_cpu,
        threads=threads,
        loops=_read_loops(),
        ops=sample.ops_delta(_prev.get("ops", {}), totals),
        gauges=gauges.read(),
        gc_collections=tuple(max(0, a - b) for a, b in zip(gc_counts, prev_gc_counts, strict=True)),
        gc_pause_ms=max(0, gc_pause_ns - prev_gc_pause) / 1_000_000,
        gc_max_pause_ms=gc_watch.take_max_ms(),
    )
    _prev.update(ts=now, ops=totals, gc=(gc_counts, gc_pause_ns))
    with _lock:
        _ring.append(s)
        _unpersisted.append(s)
        due = len(_unpersisted) >= PERF_PERSIST_EVERY_SEC
        batch = list(_unpersisted) if due else []
        if due:
            _unpersisted.clear()
    if batch and _store is not None:
        agg = sample.aggregate(batch)
        if agg is not None:
            _store.put({"kind": "sample", **agg})
    _take_stalls()
    _finish_stalls(now)
    return s


def _take_stalls() -> None:
    while not stall_watch.completed.empty():
        report = stall_watch.completed.get_nowait()
        report["schema_version"] = PERF_SCHEMA_VERSION
        report["before"] = _window(report["started_ts"] - PERF_STALL_CONTEXT_SEC, report["started_ts"])
        summary = {k: v for k, v in report.items() if k not in _REPORT_ONLY}
        summary["file"] = None
        with _lock:
            _stalls.appendleft(summary)
            _reports[report["id"]] = report
            live_ids = {s["id"] for s in _stalls}
            for old in [k for k in _reports if k not in live_ids]:
                _reports.pop(old, None)
        _awaiting_after.append(report)
        if _store is not None:
            _store.put({"kind": "stall", "ts": report["started_ts"], **summary})
        logger.warning(
            "perf: %s loop stalled %.0f ms (%d samples; top frame %s)",
            report["loop"], report["duration_ms"], report["samples"], report["top_frame"],
        )


def _finish_stalls(now: float) -> None:
    for report in list(_awaiting_after):
        if now < report["ended_ts"] + PERF_STALL_CONTEXT_SEC:
            continue
        _awaiting_after.remove(report)
        report["after"] = _window(report["ended_ts"], report["ended_ts"] + PERF_STALL_CONTEXT_SEC)
        if _store is not None and _store.put_stall(report):
            with _lock:
                for summary in _stalls:
                    if summary["id"] == report["id"]:
                        summary["file"] = str(_store.stall_path(report["id"]))


async def run() -> None:
    """Background task entry (``perf.runtime``)."""
    while True:
        await asyncio.sleep(PERF_SAMPLE_INTERVAL_SEC)
        try:
            tick()
        except Exception:
            logger.exception("perf recorder: tick failed")


def record_client(report: dict[str, Any], now: float | None = None) -> None:
    """Keep a window's latest report and queue it for the day file."""
    received = time.time() if now is None else now
    stamped = {**report, "received_ts": round(received, 3)}
    with _lock:
        _clients[str(report["window_id"])] = stamped
    if _store is not None:
        _store.put({"kind": "client", "ts": stamped["received_ts"], **stamped})


def samples(seconds: float, now: float | None = None) -> list[dict[str, Any]]:
    now = time.time() if now is None else now
    return _window(now - seconds, now + 1.0)


def clients() -> dict[str, dict[str, Any]]:
    with _lock:
        return dict(_clients)


def stall_summaries() -> list[dict[str, Any]]:
    with _lock:
        return [dict(s) for s in _stalls]


def stall_report(stall_id: str) -> dict[str, Any] | None:
    with _lock:
        report = _reports.get(stall_id)
    return dict(report) if report is not None else None


def status() -> dict[str, Any]:
    return {
        "running": _since is not None,
        "since": _since,
        "dir": str(_store.root) if _store is not None else None,
        "write_dropped": _store.write_dropped if _store is not None else 0,
        "stall_files_skipped": _store.stall_files_skipped if _store is not None else 0,
        "write_error": _store.last_error if _store is not None else None,
    }


def reset_for_tests() -> None:
    global _store, _since
    with _lock:
        _ring.clear()
        _unpersisted.clear()
        _stalls.clear()
        _reports.clear()
        _clients.clear()
    _awaiting_after.clear()
    _prev.clear()
    _store = None
    _since = None
