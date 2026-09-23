"""Diagnostics rows for the performance recorder (ADR 026). Pure.

Facts only: how busy each loop and the process were over the last minute,
whether a loop stalled and on which line, whether a queue dropped anything,
and how the desk's windows are drawing. Thresholds are first guesses until
the burst rig measures real limits.
"""
from __future__ import annotations

from typing import Any

from constants_diagnostics import (
    DIAG_GROUP_PERFORMANCE,
    DIAG_STATE_FAIL,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_UNKNOWN,
    DIAG_STATE_WARN,
)
from constants_perf import (
    PERF_CLIENT_STALE_SEC,
    PERF_DIAG_CPU_FAIL_PCT,
    PERF_DIAG_CPU_WARN_PCT,
    PERF_DIAG_SLOW_FRAMES_FAIL,
    PERF_DIAG_SLOW_FRAMES_WARN,
    PERF_DIAG_STALL_RECENT_SEC,
    PERF_DIAG_TOP_HANDLERS,
    PERF_ENV_SWITCH,
    PERF_SLOW_FRAME_MS,
    PERF_STALL_MS,
)
from diagnostics.rows import row
from perf import sample

_READ_IT = "Run `py -3 tools/perf_report.py` (or open /api/perf/live) to see which handler used the time."
_LOOP_TITLES = {"ib": "IB loop (market data)", "http": "HTTP loop (REST and sockets)"}


def _cpu_state(pct: float | None) -> str:
    if pct is None:
        return DIAG_STATE_UNKNOWN
    if pct >= PERF_DIAG_CPU_FAIL_PCT:
        return DIAG_STATE_FAIL
    if pct >= PERF_DIAG_CPU_WARN_PCT:
        return DIAG_STATE_WARN
    return DIAG_STATE_OK


def _mean(values: list[float | None]) -> float | None:
    real = [v for v in values if v is not None]
    return round(sum(real) / len(real), 1) if real else None


def _process_row(window: list[dict[str, Any]], seconds: int) -> dict[str, Any]:
    pct = _mean([s["process"]["cpu_pct"] for s in window])
    return row(
        id="perf_process_cpu",
        group=DIAG_GROUP_PERFORMANCE,
        title="API process CPU",
        state=_cpu_state(pct),
        detail=f"{pct}% of one core over the last {seconds} s" if pct is not None else "not measured yet",
        cause="Every Python thread in the API takes turns on one core (the GIL): near 100% every loop slows every other.",
        fix=_READ_IT,
        evidence={"cpu_pct": pct, "threads": window[-1]["process"]["threads"]},
    )


def _loop_row(name: str, window: list[dict[str, Any]], seconds: int) -> dict[str, Any]:
    pct = _mean([s["loops"][name]["cpu_pct"] for s in window])
    delays = [s["loops"][name]["delay_max_ms"] for s in window if s["loops"][name]["delay_max_ms"] is not None]
    worst = max(delays) if delays else None
    detail = f"{pct}% of one core" if pct is not None else "CPU not measured yet"
    if worst is not None:
        detail += f", longest callback wait {worst:.0f} ms"
    return row(
        id=f"perf_{name}_loop",
        group=DIAG_GROUP_PERFORMANCE,
        title=_LOOP_TITLES[name],
        state=_cpu_state(pct),
        detail=f"{detail} over the last {seconds} s",
        cause="A loop near a full core runs every callback late: prints, quotes and socket frames queue behind it.",
        fix=_READ_IT,
        evidence={"cpu_pct": pct, "delay_max_ms": worst},
    )


def _stall_row(stalls: list[dict[str, Any]], now: float) -> dict[str, Any]:
    recent = [s for s in stalls if s["started_ts"] >= now - PERF_DIAG_STALL_RECENT_SEC]
    minutes = PERF_DIAG_STALL_RECENT_SEC // 60
    if not recent:
        state, detail = DIAG_STATE_OK, f"no stall in the last {minutes} min ({len(stalls)} since the API started)"
    else:
        worst = max(recent, key=lambda s: s["duration_ms"])
        by_loop = ", ".join(f"{loop} {sum(1 for s in recent if s['loop'] == loop)}"
                            for loop in sample.LOOPS if any(s["loop"] == loop for s in recent))
        state = DIAG_STATE_WARN
        detail = (f"{len(recent)} in the last {minutes} min ({by_loop}); longest {worst['duration_ms']:.0f} ms "
                  f"on the {worst['loop']} loop at {worst['top_frame'] or 'a frame outside Nova'}")
    return row(
        id="perf_stalls",
        group=DIAG_GROUP_PERFORMANCE,
        title="Loop stalls",
        state=state,
        detail=detail,
        cause=f"A stall is a loop that ran no callback for over {PERF_STALL_MS:.0f} ms; "
              "its stack was sampled while it was stuck.",
        fix="GET /api/perf/stalls/<id> has the stacks; the line named here is where to look first.",
        since=recent[-1]["started_ts"] if recent else None,
        evidence={"recent": recent[:5]},
    )


def _queue_row(drop_window: list[dict[str, Any]], minutes: int) -> dict[str, Any]:
    drops = sample.drop_increase(drop_window)
    gauges = drop_window[-1]["gauges"]
    if drops:
        state = DIAG_STATE_WARN
        detail = "dropped in the last %d min: %s" % (minutes, ", ".join(f"{k} +{v:.0f}" for k, v in drops.items()))
    else:
        state, detail = DIAG_STATE_OK, f"nothing dropped in the last {minutes} min"
    return row(
        id="perf_queues",
        group=DIAG_GROUP_PERFORMANCE,
        title="Queues",
        state=state,
        detail=detail,
        cause="A queue that sheds its oldest item is a consumer that cannot keep up (a slow window, a slow disk).",
        fix=_READ_IT,
        evidence={"dropped": drops, "gauges": gauges},
    )


def _window_row(clients: dict[str, dict[str, Any]], now: float) -> dict[str, Any]:
    fresh = {k: c for k, c in clients.items() if c.get("received_ts", 0) >= now - PERF_CLIENT_STALE_SEC}
    windows = {k: c for k, c in fresh.items() if c.get("role") != "electron"}
    electron = next((c for c in fresh.values() if c.get("role") == "electron"), None)
    evidence: dict[str, Any] = {"windows": {}, "processes": (electron or {}).get("processes")}
    worst_id, worst_share = None, -1.0
    for wid, c in windows.items():
        frames, lf = c.get("frames") or {}, c.get("long_frames") or {}
        share = (frames["slow"] / frames["count"]) if frames.get("count") else None
        evidence["windows"][wid] = {
            "visible": c.get("visible"), "slow_share": round(share, 3) if share is not None else None,
            "p95_ms": frames.get("p95_ms"), "long_frames": lf.get("count"), "blocking_ms": lf.get("blocking_ms"),
            "top": lf.get("top"),
        }
        if share is not None and share > worst_share:
            worst_id, worst_share = wid, share
    if not windows:
        return row(id="perf_windows", group=DIAG_GROUP_PERFORMANCE, title="Desk windows",
                   state=DIAG_STATE_UNKNOWN,
                   detail=f"Unknown: no desk window has reported in {PERF_CLIENT_STALE_SEC:.0f} s",
                   cause="Windows report every 5 s while open; the sample desk never reports.",
                   fix="Open the desk; this row fills in on its next report.", evidence=evidence)
    if worst_id is None:
        state, detail = DIAG_STATE_OK, f"{len(windows)} window(s) reporting; none visible"
    else:
        state = (DIAG_STATE_FAIL if worst_share >= PERF_DIAG_SLOW_FRAMES_FAIL
                 else DIAG_STATE_WARN if worst_share >= PERF_DIAG_SLOW_FRAMES_WARN else DIAG_STATE_OK)
        detail = f"{len(windows)} window(s); worst {worst_id}: {worst_share:.0%} of frames slow"
    return row(
        id="perf_windows",
        group=DIAG_GROUP_PERFORMANCE,
        title="Desk windows",
        state=state,
        detail=detail,
        cause=f"A slow frame (over {PERF_SLOW_FRAME_MS:.0f} ms) is at least one dropped frame: "
              "the window's main thread was busy.",
        fix="Evidence names the scripts behind the longest frames; each pop-out is a full copy of the app.",
        evidence=evidence,
    )


def _handlers_row(window: list[dict[str, Any]], seconds: int) -> dict[str, Any]:
    top = sample.busiest(window, PERF_DIAG_TOP_HANDLERS)
    detail = ("busiest: " + ", ".join(f"{r['op']} {r['busy_ms_per_sec']:.1f} ms/s" for r in top)) if top \
        else "no timed handler ran"
    return row(
        id="perf_handlers",
        group=DIAG_GROUP_PERFORMANCE,
        title="Busiest handlers",
        state=DIAG_STATE_OK,
        detail=f"{detail} (last {seconds} s)",
        cause="Busy time per timed handler; handlers nest (ib.l1 includes the listeners it calls).",
        fix=_READ_IT,
        evidence={"top": top},
    )


def perf_rows(
    *,
    running: bool,
    window: list[dict[str, Any]],
    drop_window: list[dict[str, Any]],
    stalls: list[dict[str, Any]],
    clients: dict[str, dict[str, Any]],
    now: float,
    window_sec: int,
    drop_window_sec: int,
) -> list[dict[str, Any]]:
    if not running:
        return [row(id="perf_recorder", group=DIAG_GROUP_PERFORMANCE, title="Performance recorder",
                    state=DIAG_STATE_OFF, detail=f"turned off ({PERF_ENV_SWITCH}=0)",
                    cause="The recorder is off by configuration.",
                    fix=f"Remove {PERF_ENV_SWITCH}=0 and restart the API to record.")]
    if not window:
        return [row(id="perf_recorder", group=DIAG_GROUP_PERFORMANCE, title="Performance recorder",
                    state=DIAG_STATE_UNKNOWN, detail="Unknown: no sample yet (the first arrives a second after start)",
                    cause="The recorder takes one sample a second.", fix="Refresh in a few seconds.")]
    return [
        _process_row(window, window_sec),
        _loop_row("ib", window, window_sec),
        _loop_row("http", window, window_sec),
        _stall_row(stalls, now),
        _queue_row(drop_window or window, drop_window_sec // 60),
        _window_row(clients, now),
        _handlers_row(window, window_sec),
    ]
