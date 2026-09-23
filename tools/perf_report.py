#!/usr/bin/env python3
"""Read a day of Nova's performance recorder (ADR 026) and say where the time went.

After a laggy stretch (the open, a hot runner), this answers: which minute was
worst, which handlers used the time, where each loop stalled (with the stack),
which queues dropped, and which window drew slowly and why.

Usage:

  py -3 tools/perf_report.py                       # today, whole day
  py -3 tools/perf_report.py --date 2026-09-24 --from 09:25 --to 09:45
  py -3 tools/perf_report.py --dir F:/path/to/perf --json

The recorder's folder is asked of the running API (``/api/perf/live``) first,
then ``NOVA_CACHE_DIR``, then ``backend/.cache``; ``--dir`` overrides all.
Read-only: it never writes, and never changes the recorder.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from constants_perf import PERF_DIR_NAME, PERF_SCHEMA_VERSION, PERF_STALLS_DIR_NAME  # noqa: E402
from perf import sample  # noqa: E402

ET = ZoneInfo("America/New_York")
API = "http://127.0.0.1:8000"
TOP = 8


def _clock(ts: float) -> str:
    return datetime.fromtimestamp(ts, ET).strftime("%H:%M:%S")


def read_lines(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Lines of known schema, and how many were skipped (unknown version or unreadable)."""
    kept, skipped = [], 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            skipped += 1
            continue
        if obj.get("schema_version") != PERF_SCHEMA_VERSION:
            skipped += 1
            continue
        kept.append(obj)
    return kept, skipped


def _worst_minutes(samples: list[dict[str, Any]], top: int) -> list[dict[str, Any]]:
    by_minute: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for s in samples:
        by_minute[int(s["ts"] // 60)].append(s)
    rows = []
    for minute, group in by_minute.items():
        agg = sample.aggregate(group)
        rows.append({
            "minute": minute * 60,
            "process_cpu": agg["process"]["cpu_pct"],
            "ib_cpu": agg["loops"]["ib"]["cpu_pct"],
            "ib_delay_max_ms": agg["loops"]["ib"]["delay_max_ms"],
            "http_cpu": agg["loops"]["http"]["cpu_pct"],
            "http_delay_max_ms": agg["loops"]["http"]["delay_max_ms"],
            "stalled": agg["loops"]["ib"]["stalled"] or agg["loops"]["http"]["stalled"],
        })
    rows.sort(key=lambda r: ((r["process_cpu"] or 0), (r["ib_delay_max_ms"] or 0)), reverse=True)
    return rows[:top]


def _windows(clients: list[dict[str, Any]], top: int) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for c in clients:
        if c.get("role") == "electron":
            continue
        w = out.setdefault(c["window_id"], {
            "role": c.get("role"), "reports": 0, "seconds": 0.0, "frames": 0, "slow": 0, "p95_max_ms": None,
            "long_frames": 0, "blocking_ms": 0.0, "scripts": defaultdict(float),
            "sockets": defaultdict(int), "renders": defaultdict(int), "heap_mb_max": None,
        })
        w["reports"] += 1
        w["seconds"] += float(c.get("interval_sec") or 0)
        frames, lf = c.get("frames") or {}, c.get("long_frames") or {}
        w["frames"] += frames.get("count", 0)
        w["slow"] += frames.get("slow", 0)
        if frames.get("p95_ms") is not None:
            w["p95_max_ms"] = max(w["p95_max_ms"] or 0, frames["p95_ms"])
        w["long_frames"] += lf.get("count", 0)
        w["blocking_ms"] += lf.get("blocking_ms", 0.0)
        for script in lf.get("top") or []:
            w["scripts"][f"{script['source']} <- {script.get('invoker') or '?'}"] += script["ms"]
        for name, s in (c.get("sockets") or {}).items():
            w["sockets"][name] += s["messages"]
        for name, n in (c.get("renders") or {}).items():
            w["renders"][name] += n
        if c.get("heap_mb") is not None:
            w["heap_mb_max"] = max(w["heap_mb_max"] or 0, c["heap_mb"])
    for w in out.values():
        secs = w["seconds"] or 1.0
        w["slow_share"] = round(w["slow"] / w["frames"], 3) if w["frames"] else None
        w["scripts"] = sorted(({"script": k, "ms": round(v, 1)} for k, v in w["scripts"].items()),
                              key=lambda r: r["ms"], reverse=True)[:top]
        w["sockets_per_sec"] = {k: round(v / secs, 1) for k, v in
                                sorted(w["sockets"].items(), key=lambda kv: kv[1], reverse=True)[:top]}
        w["renders_per_sec"] = {k: round(v / secs, 1) for k, v in
                                sorted(w["renders"].items(), key=lambda kv: kv[1], reverse=True)[:top]}
        del w["sockets"], w["renders"]
    return out


def _processes(clients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    peak: dict[tuple[str, str], dict[str, Any]] = {}
    for c in clients:
        for p in c.get("processes") or []:
            key = (p.get("type") or "?", p.get("window_id") or f"pid {p.get('pid')}")
            cur = peak.setdefault(key, {"type": key[0], "window": key[1], "cpu_max": 0.0, "cpu_sum": 0.0,
                                        "n": 0, "working_set_mb_max": 0.0})
            cur["cpu_max"] = max(cur["cpu_max"], p.get("cpu_pct") or 0)
            cur["cpu_sum"] += p.get("cpu_pct") or 0
            cur["n"] += 1
            cur["working_set_mb_max"] = max(cur["working_set_mb_max"], p.get("working_set_mb") or 0)
    rows = [{**{k: v for k, v in r.items() if k not in ("cpu_sum", "n")},
             "cpu_mean": round(r["cpu_sum"] / r["n"], 1)} for r in peak.values()]
    return sorted(rows, key=lambda r: r["cpu_mean"], reverse=True)


def analyze(
    lines: list[dict[str, Any]],
    *,
    start: float | None = None,
    end: float | None = None,
    stall_reader: Callable[[str], dict[str, Any] | None] = lambda _id: None,
    top: int = TOP,
) -> dict[str, Any]:
    """The report as data. Pure apart from ``stall_reader``."""
    def inside(obj: dict[str, Any]) -> bool:
        ts = float(obj.get("ts") or 0)
        return (start is None or ts >= start) and (end is None or ts <= end)

    lines = [ln for ln in lines if inside(ln)]
    samples = sorted((ln for ln in lines if ln.get("kind") == "sample"), key=lambda s: s["ts"])
    clients = [ln for ln in lines if ln.get("kind") == "client"]
    stalls = sorted((ln for ln in lines if ln.get("kind") == "stall"),
                    key=lambda s: s.get("duration_ms") or 0, reverse=True)
    stall_rows = []
    for s in stalls[:top]:
        full = stall_reader(s["id"]) or {}
        stack = (full.get("stacks") or [{}])[0]
        stall_rows.append({**{k: s.get(k) for k in ("id", "loop", "started_ts", "duration_ms", "samples",
                                                     "top_frame")},
                           "stack": (stack.get("frames") or [])[-6:], "stack_share": stack.get("count")})
    agg = sample.aggregate(samples)
    return {
        "samples": len(samples),
        "seconds": round(sum(s["interval_sec"] for s in samples), 1),
        "first_ts": samples[0]["ts"] if samples else None,
        "last_ts": samples[-1]["ts"] if samples else None,
        "worst_minutes": _worst_minutes(samples, 3),
        "busiest": sample.busiest(samples, top),
        "stalls": {"count": len(stalls), "by_loop": {lp: sum(1 for s in stalls if s.get("loop") == lp)
                                                     for lp in sample.LOOPS}, "worst": stall_rows},
        "drops": sample.drop_increase(samples),
        "gc": agg["gc"] if agg else None,
        "windows": _windows(clients, top),
        "processes": _processes(clients),
    }


def render(report: dict[str, Any], title: str) -> str:
    out = [title]
    if not report["samples"]:
        out.append("  no samples in this range (was the API running with the recorder on?)")
    else:
        out.append(f"  {report['samples']} samples covering {report['seconds']:.0f} s, "
                   f"{_clock(report['first_ts'])}-{_clock(report['last_ts'])} ET")
    out.append("\nWorst minutes (process CPU is % of one core; every thread shares it):")
    for m in report["worst_minutes"]:
        out.append(f"  {_clock(m['minute'])}  process {m['process_cpu']}%  IB loop {m['ib_cpu']}% "
                   f"(wait max {m['ib_delay_max_ms']} ms)  HTTP loop {m['http_cpu']}% "
                   f"(wait max {m['http_delay_max_ms']} ms){'  STALLED' if m['stalled'] else ''}")
    out.append("\nBusiest handlers (handlers nest: ib.l1 includes its listeners):")
    for r in report["busiest"]:
        out.append(f"  {r['op']:<34} {r['busy_ms_per_sec']:>8.1f} ms/s  {r['calls_per_sec']:>8.1f} calls/s  "
                   f"{r['us_per_call'] or 0:>8.1f} us/call")
    st = report["stalls"]
    out.append(f"\nStalls: {st['count']} ({', '.join(f'{k} {v}' for k, v in st['by_loop'].items())})")
    for s in st["worst"]:
        out.append(f"  {_clock(s['started_ts'])} {s['loop']:<4} {s['duration_ms']:>7.0f} ms  {s['top_frame']}")
        for frame in s["stack"]:
            out.append(f"      {frame}")
    drops = report["drops"]
    out.append("\nQueue drops: " + (", ".join(f"{k} +{v:.0f}" for k, v in drops.items()) if drops else "none"))
    if report["gc"]:
        out.append(f"GC: {sum(report['gc']['collections'])} collections, {report['gc']['pause_ms']:.0f} ms paused, "
                   f"longest {report['gc']['max_pause_ms']} ms")
    out.append("\nWindows:")
    if not report["windows"]:
        out.append("  no window reported")
    for wid, w in report["windows"].items():
        share = f"{w['slow_share']:.1%}" if w["slow_share"] is not None else "n/a"
        out.append(f"  {wid} ({w['role']}): slow frames {share}, worst p95 {w['p95_max_ms']} ms, "
                   f"{w['long_frames']} long frames blocking {w['blocking_ms']:.0f} ms, heap max {w['heap_mb_max']} MB")
        for s in w["scripts"][:3]:
            out.append(f"      {s['ms']:>8.0f} ms  {s['script']}")
        if w["sockets_per_sec"]:
            out.append("      sockets/s: " + ", ".join(f"{k} {v}" for k, v in w["sockets_per_sec"].items()))
        if w["renders_per_sec"]:
            out.append("      renders/s: " + ", ".join(f"{k} {v}" for k, v in w["renders_per_sec"].items()))
    if report["processes"]:
        out.append("\nElectron processes (CPU % of one core):")
        for p in report["processes"]:
            out.append(f"  {p['window']:<14} {p['type']:<10} mean {p['cpu_mean']:>5.1f}%  max {p['cpu_max']:>5.1f}%  "
                       f"{p['working_set_mb_max']:.0f} MB")
    return "\n".join(out)


def find_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    try:
        with urllib.request.urlopen(f"{API}/api/perf/live?seconds=1", timeout=2) as resp:
            live = json.loads(resp.read().decode("utf-8"))
        if live.get("recorder", {}).get("dir"):
            return Path(live["recorder"]["dir"])
    except (urllib.error.URLError, OSError, ValueError):
        pass
    cache = os.environ.get("NOVA_CACHE_DIR") or str(REPO / "backend" / ".cache")
    return Path(cache) / PERF_DIR_NAME


def _at(day: str, hhmm: str | None) -> float | None:
    if not hhmm:
        return None
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(datetime.strptime(day, "%Y-%m-%d").date(), dtime(h, m), ET).timestamp()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=datetime.now(ET).strftime("%Y-%m-%d"), help="Eastern date (YYYY-MM-DD)")
    ap.add_argument("--from", dest="start", help="HH:MM Eastern")
    ap.add_argument("--to", dest="end", help="HH:MM Eastern")
    ap.add_argument("--dir", help="the recorder's perf folder")
    ap.add_argument("--top", type=int, default=TOP)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = find_dir(args.dir)
    path = root / f"{args.date}.jsonl"
    if not path.is_file():
        print(f"No performance file for {args.date} at {path}", file=sys.stderr)
        return 1
    lines, skipped = read_lines(path)

    def stall_reader(stall_id: str) -> dict[str, Any] | None:
        f = root / PERF_STALLS_DIR_NAME / f"{stall_id}.json"
        try:
            return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
        except (OSError, ValueError):
            return None

    report = analyze(lines, start=_at(args.date, args.start), end=_at(args.date, args.end),
                     stall_reader=stall_reader, top=args.top)
    report["skipped_lines"] = skipped
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    span = f" {args.start or '00:00'}-{args.end or '24:00'} ET" if (args.start or args.end) else ""
    print(render(report, f"Nova performance {args.date}{span}  ({path})"))
    if skipped:
        print(f"\n{skipped} line(s) skipped: unknown schema_version or unreadable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
