"""The ``pc_ports`` row: Windows' network ports in use, and the connections closed programs still hold. Pure: the
shell passes the port watch's status in (``perf.port_watch.status``).

Operator report 2026-10-14: the PC ran out of network ports at 11:45 ET -- 15,300 connections still held under
process ids that no longer existed -- and every new connection failed, IB Gateway's and the backend's own
included, so the backend restarted 19 times in 40 minutes. "just make sure no leakage happens".

The living programs holding the most are named only in ``fix``, and the row sits in the ``process`` group, as
the ``pc_memory`` row does: an issue filed from the desk prints every row's detail and cause, and what else
runs on the operator's PC is not Nova's to publish.
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
from constants_perf import (
    PERF_PORTS_CLOSED_WARN,
    PERF_PORTS_CRITICAL_PCT,
    PERF_PORTS_PRESSURE_PCT,
    PERF_PORTS_STALE_SEC,
)
from diagnostics.rows import row
from perf.port_watch import top_words

ROW_ID = "pc_ports"
ROW_TITLE = "PC network ports"

_RESTART = ("Restart the PC at a quiet moment -- nothing else frees a closed program's connections. IB Gateway "
            "needs its login after a restart.")


def ports_rows(*, status: dict[str, Any], now: float | None = None) -> list[dict[str, Any]]:
    t = time.time() if now is None else now
    read = status.get("last")
    base = dict(id=ROW_ID, group=DIAG_GROUP_PROCESS, title=ROW_TITLE, evidence=read)
    if not status.get("available"):
        return [row(**base, state=DIAG_STATE_OFF, detail="Not on Windows",
                    cause="The port watch reads Windows' own TCP tables.", fix="Nothing to do.")]
    if read is None:
        return [row(**base, state=DIAG_STATE_UNKNOWN, detail="The port watch has not read the PC yet",
                    cause="It reads 20 s after the backend starts, then every minute, with the performance "
                          "recorder (NOVA_PERF=0 turns both off).",
                    fix="Reload backend if this lasts more than two minutes.")]
    age = t - float(read["ts"])
    if age > PERF_PORTS_STALE_SEC:
        return [row(**base, state=DIAG_STATE_UNKNOWN, detail=f"The last reading is {age / 60:.0f} min old",
                    cause="The port watch stopped reading; the API log says why.", fix="Reload backend.")]
    pct, closed = read["pct"], read["closed"]["connections"]
    detail = (f"Network ports {read['in_use']:,} of {read['range']['count']:,} in use ({pct}%); {closed:,} held by "
              "programs that have closed")
    holders = top_words(read)
    biggest = f" Holding the most now: {holders}." if holders else ""
    if pct >= PERF_PORTS_CRITICAL_PCT:
        return [row(**base, state=DIAG_STATE_FAIL, detail=f"{detail} -- nearly out",
                    cause=("When none are left every new connection fails -- IB Gateway's, the desk's and the "
                           "backend's own (2026-10-14: no Time & Sales or Level 2, the backend restarted 19 times)."),
                    fix=(_RESTART if closed >= PERF_PORTS_CLOSED_WARN else
                         "Close the program holding the most (Task Manager > Details).") + biggest)]
    if closed >= PERF_PORTS_CLOSED_WARN:
        return [row(**base, state=DIAG_STATE_WARN, detail=detail,
                    cause=("Windows keeps connections of programs that have closed, and they only grow until the "
                           "ports run out (a network driver holding them is the usual cause)."),
                    fix=_RESTART + biggest)]
    if pct >= PERF_PORTS_PRESSURE_PCT:
        return [row(**base, state=DIAG_STATE_WARN, detail=detail,
                    cause="Living programs hold most of them. Past the last one, new connections fail anywhere.",
                    fix=f"Close or restart the program holding the most (Task Manager > Details).{biggest}")]
    return [row(**base, state=DIAG_STATE_OK, detail=detail,
                cause="Measured every minute from Windows' TCP tables.", fix=f"Nothing to do.{biggest}")]
