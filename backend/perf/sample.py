"""Sample shape, per-interval deltas, aggregates and summaries (ADR 026). Pure."""
from __future__ import annotations

from typing import Any

from constants_perf import PERF_SCHEMA_VERSION

LOOPS = ("ib", "http")


def ops_delta(
    prev: dict[str, tuple[int, int]],
    now: dict[str, tuple[int, int]],
) -> dict[str, dict[str, float]]:
    """Calls and busy ms per operation between two ``op_metrics.totals()`` readings.

    Operations that did not run are left out. A total that went backwards
    (a test reset) counts from zero.
    """
    out: dict[str, dict[str, float]] = {}
    for name, (count, total_ns) in now.items():
        prev_count, prev_ns = prev.get(name, (0, 0))
        calls, busy_ns = count - prev_count, total_ns - prev_ns
        if calls < 0 or busy_ns < 0:
            calls, busy_ns = count, total_ns
        if calls > 0:
            out[name] = {"calls": calls, "busy_ms": round(busy_ns / 1_000_000, 3)}
    return out


def build(
    *,
    ts: float,
    interval_sec: float,
    process_cpu_pct: float | None,
    threads: int,
    loops: dict[str, dict[str, Any]],
    ops: dict[str, dict[str, float]],
    gauges: dict[str, float],
    gc_collections: tuple[int, int, int],
    gc_pause_ms: float,
    gc_max_pause_ms: float,
) -> dict[str, Any]:
    return {
        "schema_version": PERF_SCHEMA_VERSION,
        "ts": round(ts, 3),
        "interval_sec": round(interval_sec, 3),
        "process": {"cpu_pct": process_cpu_pct, "threads": threads},
        "loops": {name: dict(loops.get(name) or {"cpu_pct": None, "delay_max_ms": None, "stalled": False})
                  for name in LOOPS},
        "ops": ops,
        "gauges": gauges,
        "gc": {
            "collections": list(gc_collections),
            "pause_ms": round(gc_pause_ms, 2),
            "max_pause_ms": round(gc_max_pause_ms, 2),
        },
    }


def _mean(values: list[float | None]) -> float | None:
    real = [v for v in values if v is not None]
    return round(sum(real) / len(real), 1) if real else None


def _max(values: list[float | None]) -> float | None:
    real = [v for v in values if v is not None]
    return max(real) if real else None


def aggregate(samples: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One sample standing for several: ops and gc summed, CPU averaged,
    delays maxed, gauges as of the last."""
    if not samples:
        return None
    last = samples[-1]
    ops: dict[str, dict[str, float]] = {}
    for s in samples:
        for name, op in s["ops"].items():
            acc = ops.setdefault(name, {"calls": 0, "busy_ms": 0.0})
            acc["calls"] += op["calls"]
            acc["busy_ms"] = round(acc["busy_ms"] + op["busy_ms"], 3)
    loops = {
        name: {
            "cpu_pct": _mean([s["loops"][name]["cpu_pct"] for s in samples]),
            "delay_max_ms": _max([s["loops"][name]["delay_max_ms"] for s in samples]),
            "stalled": any(s["loops"][name]["stalled"] for s in samples),
        }
        for name in LOOPS
    }
    collections = [sum(s["gc"]["collections"][g] for s in samples) for g in range(3)]
    return {
        "schema_version": PERF_SCHEMA_VERSION,
        "ts": last["ts"],
        "interval_sec": round(sum(s["interval_sec"] for s in samples), 3),
        "process": {
            "cpu_pct": _mean([s["process"]["cpu_pct"] for s in samples]),
            "threads": last["process"]["threads"],
        },
        "loops": loops,
        "ops": ops,
        "gauges": dict(last["gauges"]),
        "gc": {
            "collections": collections,
            "pause_ms": round(sum(s["gc"]["pause_ms"] for s in samples), 2),
            "max_pause_ms": _max([s["gc"]["max_pause_ms"] for s in samples]) or 0.0,
        },
    }


def drop_increase(samples: list[dict[str, Any]]) -> dict[str, float]:
    """How much each ``*dropped`` gauge grew across ``samples`` (only growth)."""
    if len(samples) < 2:
        return {}
    first, last = samples[0]["gauges"], samples[-1]["gauges"]
    out: dict[str, float] = {}
    for name, value in last.items():
        if name.endswith("dropped"):
            grew = value - first.get(name, 0)  # a counter appears on its first drop
            if grew > 0:
                out[name] = grew
    return out


def busiest(samples: list[dict[str, Any]], top: int) -> list[dict[str, float]]:
    """Operations by busy time per second over ``samples``, busiest first."""
    wall = sum(s["interval_sec"] for s in samples)
    if wall <= 0:
        return []
    agg = aggregate(samples) or {"ops": {}}
    rows = [
        {
            "op": name,
            "busy_ms_per_sec": round(op["busy_ms"] / wall, 2),
            "calls_per_sec": round(op["calls"] / wall, 1),
            "us_per_call": round(1000.0 * op["busy_ms"] / op["calls"], 1) if op["calls"] else None,
        }
        for name, op in agg["ops"].items()
    ]
    rows.sort(key=lambda r: r["busy_ms_per_sec"], reverse=True)
    return rows[:top]
