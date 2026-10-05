"""The ``process_priority`` and ``perf_freezes`` rows (ADR 045). Pure: the shell passes the views in.

- ``process_priority``: what the API, the IB Gateway and IBC's launch loop run at, and how often
  something on the PC lowered them (``process_priority.trading_path.view``). 2026-10-05: an ASUS
  game booster's PC ran ``explorer.exe`` BelowNormal, and the API read BelowNormal minutes after it
  logged Normal.
- ``perf_freezes``: the last time the whole process stopped long enough for the C-level watchdog to
  write every thread's stack (``perf.freeze_watch.status``).
"""
from __future__ import annotations

import time
from typing import Any

from constants_diagnostics import (
    DIAG_GROUP_PERFORMANCE,
    DIAG_GROUP_PROCESS,
    DIAG_STATE_FAIL,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_UNKNOWN,
    DIAG_STATE_WARN,
)
from constants_perf import PERF_DIAG_FREEZE_RECENT_SEC
from diagnostics.rows import row

_LOW = ("Idle", "BelowNormal")


def priority_rows(*, view: dict[str, Any]) -> list[dict[str, Any]]:
    procs = view.get("processes") or []
    evidence = {"processes": procs, "checked_at": view.get("checked_at"), "running": view.get("running")}
    base = dict(id="process_priority", group=DIAG_GROUP_PROCESS, title="Trading path priority", evidence=evidence)
    if not view.get("enabled"):
        return [row(**base, state=DIAG_STATE_OFF, detail="Off (not Windows, or NOVA_PROCESS_PRIORITY=0)",
                    cause="Nova does not manage process priority here.", fix="Nothing to do.")]
    if not view.get("running") or not procs:
        return [row(**base, state=DIAG_STATE_UNKNOWN, detail="The priority keeper has not read the processes yet",
                    cause="It starts with the backend and reads every 2 s.",
                    fix="Reload backend if this lasts more than a minute.")]
    low = [p for p in procs if p.get("priority") in _LOW]
    lowered = [p for p in procs if p.get("raised")]
    refused = [p for p in procs if p.get("error")]
    words = ", ".join(f"{p['role']} {p['priority']}" for p in procs)
    if low or refused:
        state = DIAG_STATE_FAIL
        detail = "Below Normal: " + ", ".join(f"{p['role']} ({p['name']})" for p in low or refused)
        cause = ("Windows refused to raise them: " + "; ".join(p["error"] for p in refused)) if refused else (
            "They run below background work, so builds, browsers and other apps take the CPU first.")
        fix = "Close or reconfigure the software that lowers process priority (a game booster), then Reload backend."
    elif lowered:
        state = DIAG_STATE_WARN
        times = sum(int(p["raised"]) for p in lowered)
        detail = f"{words}. Lowered by something on this PC {times} times since start; Nova raised it back"
        cause = ("Software on this PC lowers processes after they start (on 2026-10-05: an ASUS game booster "
                 "ran explorer.exe and everything it started at BelowNormal). Nova checks every 2 s.")
        fix = "Exclude Nova, IB Gateway and Java from that software's priority control, or turn it off."
    else:
        state = DIAG_STATE_OK
        detail = words
        cause = "The API and IB Gateway run above background work (ADR 045)."
        fix = "Nothing to do."
    return [row(**base, state=state, detail=detail, cause=cause, fix=fix)]


def freeze_rows(*, status: dict[str, Any], now: float | None = None) -> list[dict[str, Any]]:
    t = time.time() if now is None else now
    last = status.get("last")
    base = dict(id="perf_freezes", group=DIAG_GROUP_PERFORMANCE, title="Whole-process freezes",
                evidence={"running": status.get("running"), "count": status.get("count"), "last": last})
    if not status.get("running"):
        return [row(**base, state=DIAG_STATE_UNKNOWN, detail="The freeze watch is not running",
                    cause="It starts with the performance recorder (NOVA_PERF=0 turns both off).",
                    fix="Reload backend.")]
    if last and t - float(last.get("noticed_at") or 0) < PERF_DIAG_FREEZE_RECENT_SEC:
        return [row(**base, state=DIAG_STATE_FAIL,
                    detail=f"The backend stopped for {last['frozen_sec']} s ({status.get('count')} since start)",
                    cause=("Every thread stopped: one long call held Python's lock, or Windows did not run the "
                           "process. Orders wait while it lasts (ADR 045)."),
                    fix=f"Every thread's stack is in perf/freezes/{last['file']} at byte {last['offset']}; "
                        "attach it to an issue.")]
    return [row(**base, state=DIAG_STATE_OK,
                detail=f"No freeze in the last {PERF_DIAG_FREEZE_RECENT_SEC // 60:.0f} minutes"
                       + (f" ({status.get('count')} since start)" if status.get("count") else ""),
                cause="The process kept running.", fix="Nothing to do.")]
