"""The port watch: how many of Windows' network ports are in use, and how many closed programs still hold
(operator report 2026-10-14).

That day the PC ran out: 16,400 TCP connections against 16,384 dynamic ports, 15,300 of them still
``ESTABLISHED`` under 755 process ids that no longer existed, leaking since the boot four days before. Every new
connection failed -- IB Gateway's, the desk's and the API guard's own probe -- and nothing on the desk had said
the ports were going. "just make sure no leakage happens": Nova cannot stop Windows keeping them, but it can say
so long before the last one goes.

Once a minute, on a worker thread (the TCP tables and the process list take a few ms), one reading: the
connections whose local port is in the dynamic range, the ones held under exited process ids, and the living
programs holding the most. Each reading is one ``kind: "ports"`` line in the perf day file, the last one answers
the ``pc_ports`` diagnostics row, and the API log warns once per episode with the counts only (an issue dump
prints the log). It measures and never acts. No address, port or command line is kept.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import Counter
from collections.abc import Iterable
from typing import Any

from constants_perf import (
    PERF_PORTS_CLOSED_WARN,
    PERF_PORTS_EVERY_SEC,
    PERF_PORTS_FIRST_AFTER_SEC,
    PERF_PORTS_PRESSURE_PCT,
    PERF_PORTS_REARM_PCT,
    PERF_PORTS_SCHEMA_VERSION,
    PERF_PORTS_TOP,
)

logger = logging.getLogger(__name__)

LISTEN = 2                              # MIB_TCP_STATE_LISTEN
_IDLE_PIDS = {0, 4}                     # TIME_WAIT rows and the kernel: owned by nobody that could have closed

_lock = threading.Lock()
_last: dict[str, Any] | None = None
_running = False
_range: tuple[int, int, str] | None = None
_pressure = False                       # inside an episode (warned once)


def reading(*, now: float, conns: Iterable[Any], procs: Iterable[Any], dyn: tuple[int, int, str]) -> dict[str, Any]:
    """One reading from the TCP tables (``winapi.tcp.Conn``), the process list (``winapi.processes.Proc``) and the
    dynamic range. Pure."""
    start, count, source = dyn
    names = {int(p.pid): str(p.name) for p in procs}
    in_use = closed = 0
    closed_pids: set[int] = set()
    held: Counter[str] = Counter()
    for c in conns:
        if c.state == LISTEN:
            continue
        if start <= c.local_port < start + count:
            in_use += 1
        if c.pid in _IDLE_PIDS:
            continue
        name = names.get(c.pid)
        if name is None:
            closed += 1
            closed_pids.add(c.pid)
        else:
            held[name] += 1
    return {
        "kind": "ports", "schema_version": PERF_PORTS_SCHEMA_VERSION, "ts": round(now, 3),
        "range": {"start": start, "count": count, "source": source},
        "in_use": in_use, "pct": round(100 * in_use / count) if count else 0,
        "closed": {"connections": closed, "pids": len(closed_pids)},
        "top": [{"name": n, "count": k} for n, k in held.most_common(PERF_PORTS_TOP)],
    }


def top_words(read: dict[str, Any]) -> str:
    """The living programs holding the most connections, for the row's fix."""
    return ", ".join(f"{t['name']} {t['count']:,}" for t in read.get("top") or [])


def _warn(read: dict[str, Any]) -> None:
    """Once per episode: the dynamic ports past PERF_PORTS_PRESSURE_PCT, or the closed programs' connections past
    PERF_PORTS_CLOSED_WARN. Counts only."""
    global _pressure
    pct, closed = read["pct"], read["closed"]["connections"]
    if (pct >= PERF_PORTS_PRESSURE_PCT or closed >= PERF_PORTS_CLOSED_WARN) and not _pressure:
        _pressure = True
        logger.warning("PC network ports: %s of %s dynamic ports in use (%d%%); %s connections held by %s programs "
                       "that have closed -- Windows frees those only on a restart (the pc_ports row)",
                       f"{read['in_use']:,}", f"{read['range']['count']:,}", pct, f"{closed:,}",
                       read["closed"]["pids"])
    elif pct < PERF_PORTS_REARM_PCT and closed < PERF_PORTS_CLOSED_WARN:
        _pressure = False


def tick(now: float | None = None) -> dict[str, Any] | None:
    """Take one reading, keep it, write it to the day file and warn as due. None off Windows."""
    global _last, _range
    from winapi import available, processes, tcp

    if not available():
        return None
    now = time.time() if now is None else now
    if _range is None:
        _range = tcp.dynamic_range()     # once per process: netsh is a child process
    from perf import recorder

    read = reading(now=now, conns=tcp.connections(), procs=processes.snapshot(), dyn=_range)
    with _lock:
        _last = read
    recorder.persist(read)
    _warn(read)
    return read


def status() -> dict[str, Any]:
    """The ``pc_ports`` row's input: whether the watch runs here, and its last reading."""
    from winapi import available

    with _lock:
        return {"available": available(), "running": _running, "every_sec": PERF_PORTS_EVERY_SEC, "last": _last}


async def run() -> None:
    """Background task entry (``perf.runtime``): a reading shortly after start, then every minute, off the loop."""
    global _running
    _running = True
    try:
        await asyncio.sleep(PERF_PORTS_FIRST_AFTER_SEC)
        while True:
            try:
                await asyncio.to_thread(tick)
            except Exception:
                logger.exception("perf: port reading failed")
            await asyncio.sleep(PERF_PORTS_EVERY_SEC)
    finally:
        _running = False


def reset_for_tests() -> None:
    global _last, _running, _range, _pressure
    with _lock:
        _last = None
    _running = _pressure = False
    _range = None
