"""The ``pc_memory`` row: the PC's memory, Nova's share of it, and who holds the rest. Pure: the shell passes
the memory watch's status in (``perf.memory_watch.status``).

Operator report 2026-10-11: "nova keeps driving the ram higher and higher". The PC was at 72 of 80 GB
committed; Nova held 3.4 GB of it, and nothing on the desk said so.

The other programs are named only in ``fix``, and the row sits in the ``process`` group: an issue filed
from the desk prints every row's detail and cause, and the evidence of rows outside that group, into a
public page, and what else runs on the operator's PC is not Nova's to publish.
"""
from __future__ import annotations

import time
from typing import Any

from constants_diagnostics import (
    DIAG_GROUP_PROCESS,
    DIAG_STATE_FAIL,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_UNKNOWN,
    DIAG_STATE_WARN,
)
from constants_perf import PERF_MEMORY_CRITICAL_PCT, PERF_MEMORY_PRESSURE_PCT, PERF_MEMORY_STALE_SEC
from diagnostics.rows import row
from perf.memory_notice import biggest_view, biggest_words
from perf.memory_watch import LEAK_LINES, PART_WORDS, gb, nova_words, others_words, pressure_pct

ROW_ID = "pc_memory"
ROW_TITLE = "PC memory"

_LEAK_FIX = {
    "api": ("GET /api/perf/heap names the biggest holders; send it with Help > Report an issue. Reload backend "
            "gives the memory back."),
    "desk": "Reload the desk (Ctrl+R) gives it back; Help > Report an issue with this row says when it grew.",
}


def memory_rows(*, status: dict[str, Any], now: float | None = None) -> list[dict[str, Any]]:
    t = time.time() if now is None else now
    read = status.get("last")
    base = dict(id=ROW_ID, group=DIAG_GROUP_PROCESS, title=ROW_TITLE, evidence=read)
    if not status.get("available"):
        return [row(**base, state=DIAG_STATE_OFF, detail="Not on Windows",
                    cause="The memory watch reads Windows' own memory counters.", fix="Nothing to do.")]
    if read is None:
        return [row(**base, state=DIAG_STATE_UNKNOWN, detail="The memory watch has not read the PC yet",
                    cause="It reads 20 s after the backend starts, then every minute, with the performance "
                          "recorder (NOVA_PERF=0 turns both off).",
                    fix="Reload backend if this lasts more than two minutes.")]
    age = t - float(read["ts"])
    if age > PERF_MEMORY_STALE_SEC:
        return [row(**base, state=DIAG_STATE_UNKNOWN, detail=f"The last reading is {age / 60:.0f} min old",
                    cause="The memory watch stopped reading; the API log says why.", fix="Reload backend.")]
    pc = read.get("pc")
    nova = nova_words(read)
    rest = others_words(read)
    leaks = [(part, read["nova"]["parts"].get(part) or 0, line) for part, line in LEAK_LINES.items()
             if (read["nova"]["parts"].get(part) or 0) >= line]
    if leaks:
        part, held, line = leaks[0]
        return [row(**base, state=DIAG_STATE_FAIL,
                    detail=f"Nova's {PART_WORDS[part]} holds {gb(held)}, past its {gb(line)} line. {nova}",
                    cause=("Memory this part of Nova keeps and does not free: a leak in Nova. In the week to "
                           "2026-10-11 the API never held more than 3.4 GB and the desk 2.8 GB."),
                    fix=_LEAK_FIX[part])]
    if pc is None:
        return [row(**base, state=DIAG_STATE_UNKNOWN, detail=f"Windows did not report the PC's memory. {nova}",
                    cause="GlobalMemoryStatusEx failed.", fix="Nothing to do unless it lasts.")]
    pct = pressure_pct(pc) or 0
    used = (f"PC memory {pc['load_pct']}% in use, {gb(pc['commit_used_mb'])} of {gb(pc['commit_limit_mb'])} "
            f"committed")
    share = round(100 * read["nova"]["total_mb"] / pc["commit_used_mb"]) if pc.get("commit_used_mb") else 0
    who = f"{nova}, {share}% of it; other programs {gb(read['others_total_mb'])}"
    biggest = f"The biggest others: {rest}." if rest else "No other program could be read."
    if read.get("biggest"):                         # readings from before 2026-10-15 have none
        biggest += " " + biggest_words(biggest_view(read, t), None)
    if pct >= PERF_MEMORY_CRITICAL_PCT:
        return [row(**base, state=DIAG_STATE_FAIL, detail=f"{used}: nearly out. {who}",
                    cause=("With RAM this full Windows pages and every program slows (2026-10-15: the TraderTV "
                           "page went blank); when the commit charge reaches its limit, any program's next "
                           "allocation fails -- the API's, IB Gateway's and the desk's included."),
                    fix=f"{biggest} Close the biggest now (Task Manager > Details, by PID).")]
    if pct >= PERF_MEMORY_PRESSURE_PCT:
        nova_most = share >= 50
        return [row(**base, state=DIAG_STATE_WARN, detail=f"{used}. {who}",
                    cause=("Nova holds most of it." if nova_most else
                           "Other programs hold most of it. Past the limit, allocations fail in any program, "
                           "Nova and IB Gateway included."),
                    fix=("Reload backend, then Help > Report an issue if it climbs back." if nova_most else
                         f"{biggest} Close or stop the biggest of them (Task Manager > Details, by PID)."))]
    return [row(**base, state=DIAG_STATE_OK, detail=f"{used}. {who}",
                cause="Nova's share is measured every minute, by process.", fix=f"Nothing to do. {biggest}")]
