"""The memory watch: the PC's memory, Nova's share of it, and who holds the rest (operator report 2026-10-11).

"nova keeps driving the ram higher and higher": the PC was at 72 of 80 GB committed, and nothing on
the desk could say whose memory it was. It was a day-file reader under test in another session
(8.3 GB, growing) and other programs (28 GB of Python alone); the API held 1.9 GB and the desk 1.3 GB.

Once a minute, on a worker thread (a scan of ~500 processes takes ~100 ms), this reads:
- the PC (``winapi.memory.pc_memory``);
- every process's private bytes, the memory it committed for itself -- what a leak grows;
- Nova's processes by pid: the API (this process), the processes it started (a Sim import), the
  desk's Electron processes (pids from the desk's own perf reports) and IB Gateway with IBC's
  loop (the priority keeper's);
- the biggest other programs, grouped by image name.

Each reading is one ``kind: "memory"`` line in the perf day file, the last one answers the
``pc_memory`` diagnostics row, and the API log warns once per episode when the PC passes
``PERF_MEMORY_PRESSURE_PCT`` or once per run when a Nova part passes its leak line. A process
Windows will not open is counted as unreadable, never as 0. No command line is read.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

from constants_perf import (
    PERF_MEMORY_API_LEAK_MB,
    PERF_MEMORY_CLIENT_FRESH_SEC,
    PERF_MEMORY_DESK_LEAK_MB,
    PERF_MEMORY_EVERY_SEC,
    PERF_MEMORY_FIRST_AFTER_SEC,
    PERF_MEMORY_PRESSURE_PCT,
    PERF_MEMORY_REARM_PCT,
    PERF_MEMORY_SCHEMA_VERSION,
    PERF_MEMORY_TOP,
)

logger = logging.getLogger(__name__)

PARTS = ("api", "children", "desk", "gateway")
PART_WORDS = {"api": "API", "children": "Sim import", "desk": "desk", "gateway": "Gateway"}
LEAK_LINES = {"api": PERF_MEMORY_API_LEAK_MB, "desk": PERF_MEMORY_DESK_LEAK_MB}
_MB = 2**20

_lock = threading.Lock()
_last: dict[str, Any] | None = None
_running = False
_pressure = False                       # inside a pressure episode (warned once)
_leak_warned: set[str] = set()          # Nova parts warned about in this run


def _descendants(root: int, procs: Iterable[Any], created: Callable[[int], float | None]) -> set[int]:
    """Every pid started (directly or not) by ``root``, from one snapshot.

    Windows reuses pids and keeps a child's parent pid after the parent exits, so a child counts only
    when it was created after its parent (an unknown start time never counts)."""
    children: dict[int, list[int]] = {}
    for p in procs:
        if p.pid != p.ppid:
            children.setdefault(p.ppid, []).append(p.pid)
    out: set[int] = set()
    todo = [(root, pid) for pid in children.get(root, ())]
    while todo:
        parent, pid = todo.pop()
        if pid in out or pid == root:
            continue
        born, parent_born = created(pid), created(parent)
        if born is None or parent_born is None or born < parent_born:
            continue
        out.add(pid)
        todo.extend((pid, child) for child in children.get(pid, ()))
    return out


def desk_pids(clients: dict[str, dict[str, Any]], now: float) -> set[int]:
    """The desk's Electron processes, from window reports younger than ``PERF_MEMORY_CLIENT_FRESH_SEC``."""
    out: set[int] = set()
    for report in clients.values():
        if now - float(report.get("received_ts") or 0) > PERF_MEMORY_CLIENT_FRESH_SEC:
            continue
        for proc in report.get("processes") or []:
            if isinstance(proc.get("pid"), int):
                out.add(proc["pid"])
    return out


def gateway_pids(view: dict[str, Any]) -> set[int]:
    """IB Gateway and IBC's launch loop, as the priority keeper found them (never guessed from a name)."""
    return {int(p["pid"]) for p in view.get("processes") or [] if p.get("role") != "api" and p.get("pid")}


def reading(*, now: float, api_pid: int, procs: list[Any], private_of: Callable[[int], int | None],
            created: Callable[[int], float | None], desk: set[int], gateway: set[int],
            pc: dict[str, int] | None) -> dict[str, Any]:
    """One reading: the PC, Nova's processes by part, and the biggest other programs by image name.

    A process has one part, the first that claims it: Gateway, the API, what the API started, then
    the desk with what its processes started (the packaged desk starts the API, which stays the API)."""
    role_of: dict[int, str] = {}
    for pid in desk:
        role_of[pid] = "desk"
        role_of.update((child, "desk") for child in _descendants(pid, procs, created))
    role_of.update((child, "children") for child in _descendants(api_pid, procs, created))
    role_of[api_pid] = "api"
    role_of.update((pid, "gateway") for pid in gateway)
    nova: list[dict[str, Any]] = []
    others: dict[str, dict[str, Any]] = {}
    unreadable = 0
    for p in procs:
        if p.pid == 0:
            continue
        size = private_of(p.pid)
        if size is None:
            unreadable += 1
            continue
        mb = round(size / _MB)
        role = role_of.get(p.pid)
        if role is not None:
            nova.append({"role": role, "pid": p.pid, "name": p.name, "private_mb": mb})
            continue
        key = p.name.lower()
        group = others.setdefault(key, {"name": p.name, "count": 0, "private_mb": 0, "largest_pid": None,
                                        "largest_mb": -1})
        group["count"] += 1
        group["private_mb"] += mb
        if mb > group["largest_mb"]:
            group["largest_pid"], group["largest_mb"] = p.pid, mb
    parts = {part: sum(n["private_mb"] for n in nova if n["role"] == part) for part in PARTS}
    ranked = sorted(others.values(), key=lambda g: -g["private_mb"])
    return {
        "kind": "memory",
        "schema_version": PERF_MEMORY_SCHEMA_VERSION,
        "ts": round(now, 3),
        "pc": pc,
        "nova": {"total_mb": sum(parts.values()), "parts": parts,
                 "processes": sorted(nova, key=lambda n: -n["private_mb"])},
        "others": ranked[:PERF_MEMORY_TOP],
        "others_total_mb": sum(g["private_mb"] for g in ranked),
        "unreadable": unreadable,
    }


def pressure_pct(pc: dict[str, int] | None) -> int | None:
    """The higher of RAM in use and the commit charge's share of its limit; None when unknown."""
    if not pc:
        return None
    commit = round(100 * pc["commit_used_mb"] / pc["commit_limit_mb"]) if pc.get("commit_limit_mb") else 0
    return max(int(pc.get("load_pct") or 0), commit)


def gb(mb: float) -> str:
    return f"{mb / 1024:.1f} GB"


def nova_words(read: dict[str, Any]) -> str:
    """``Nova 4.1 GB (API 1.9, desk 1.4, Gateway 0.4)`` -- parts holding nothing are left out."""
    parts = read["nova"]["parts"]
    named = ", ".join(f"{PART_WORDS[p]} {parts[p] / 1024:.1f}" for p in PARTS if parts.get(p))
    return f"Nova {gb(read['nova']['total_mb'])}" + (f" ({named})" if named else "")


def others_words(read: dict[str, Any], top: int = 3) -> str:
    """``python3.13.exe x40 30.7 GB (largest pid 59984, 1.4 GB)``, the biggest first."""
    words = []
    for g in read["others"][:top]:
        many = f" x{g['count']}" if g["count"] > 1 else ""
        largest = f" (largest pid {g['largest_pid']}, {gb(g['largest_mb'])})" if g["count"] > 1 else f" (pid {g['largest_pid']})"
        words.append(f"{g['name']}{many} {gb(g['private_mb'])}{largest}")
    return "; ".join(words)


def _warn(read: dict[str, Any]) -> None:
    """Once per pressure episode, and once per run per Nova part past its leak line."""
    global _pressure
    pct = pressure_pct(read["pc"])
    if pct is not None:
        if pct >= PERF_MEMORY_PRESSURE_PCT and not _pressure:
            _pressure = True
            pc = read["pc"]
            logger.warning("PC memory %d%% (RAM %d%% in use, commit %s of %s): %s; other programs %s (named in the "
                           "pc_memory row's fix and the perf day file, never here: an issue dump prints this log)",
                           pct, pc["load_pct"], gb(pc["commit_used_mb"]), gb(pc["commit_limit_mb"]),
                           nova_words(read), gb(read["others_total_mb"]))
        elif pct < PERF_MEMORY_REARM_PCT:
            _pressure = False
    for part, line in LEAK_LINES.items():
        held = read["nova"]["parts"].get(part) or 0
        if held >= line and part not in _leak_warned:
            _leak_warned.add(part)
            logger.warning("Nova's %s holds %s, past its %s leak line: memory it keeps and does not free",
                           PART_WORDS[part], gb(held), gb(line))


def tick(now: float | None = None) -> dict[str, Any] | None:
    """Take one reading, keep it, write it to the day file and warn as due. None off Windows."""
    global _last
    from winapi import available, memory, processes

    if not available():
        return None
    now = time.time() if now is None else now
    from perf import recorder
    from process_priority import trading_path

    read = reading(now=now, api_pid=os.getpid(), procs=processes.snapshot(), private_of=memory.private_bytes,
                   created=processes.created_at, desk=desk_pids(recorder.clients(), now),
                   gateway=gateway_pids(trading_path.view()), pc=memory.pc_memory())
    with _lock:
        _last = read
    recorder.persist(read)
    _warn(read)
    return read


def status() -> dict[str, Any]:
    """The ``pc_memory`` row's input: whether the watch runs here, and its last reading."""
    from winapi import available

    with _lock:
        return {"available": available(), "running": _running, "every_sec": PERF_MEMORY_EVERY_SEC, "last": _last}


async def run() -> None:
    """Background task entry (``perf.runtime``): a reading shortly after start, then every minute, off the loop."""
    global _running
    _running = True
    try:
        await asyncio.sleep(PERF_MEMORY_FIRST_AFTER_SEC)
        while True:
            try:
                await asyncio.to_thread(tick)
            except Exception:
                logger.exception("perf: memory reading failed")
            await asyncio.sleep(PERF_MEMORY_EVERY_SEC)
    finally:
        _running = False


def reset_for_tests() -> None:
    global _last, _running, _pressure
    with _lock:
        _last = None
    _running = _pressure = False
    _leak_warned.clear()
