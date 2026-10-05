"""Keep the trading path above background work, every few seconds (ADR 045).

``normal.raise_to_normal`` raises the API once, at start. That was not enough on 2026-10-05: the API
logged "CPU Normal" at 14:17:12 and read BelowNormal minutes later, as did the IB Gateway, while
``explorer.exe`` -- and so every program the operator opened -- ran BelowNormal beside an ASUS game
booster. So a daemon thread (``nova-priority``) reads each process of the trading path every
``PROCESS_PRIORITY_RECHECK_SEC`` and raises what it finds lower, never lowering anything:

- the API: Above Normal, normal I/O and memory priority, out of Windows power throttling;
- the IB Gateway (``ibkr.gateway_process``): Above Normal, normal I/O and memory priority;
- IBC's launch loop above it (the Gateway's relaunch inherits from it): Normal on all three.

The API's own IB and socket loop threads are raised to Above Normal within it once
(``raise_current_thread``). A process found lower than it was left is counted (``lowered``) and
logged -- at WARNING once per process and every ``PROCESS_PRIORITY_WARN_EVERY_SEC`` -- so what
keeps lowering Nova shows on the checklist (``view()``, the ``process_priority`` row).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from constants_priority import (
    PROCESS_PRIORITY_DISCOVER_SEC,
    PROCESS_PRIORITY_ENV,
    PROCESS_PRIORITY_IBC_MAX_DEPTH,
    PROCESS_PRIORITY_IBC_PATTERN,
    PROCESS_PRIORITY_RECHECK_SEC,
    PROCESS_PRIORITY_WARN_EVERY_SEC,
)

logger = logging.getLogger(__name__)

_IBC = re.compile(PROCESS_PRIORITY_IBC_PATTERN)


@dataclass
class _Tracked:
    role: str            # api | gateway | ibc_loop
    pid: int
    name: str
    target: int          # the CPU class it is kept at or above
    unthrottle: bool = False
    priority: str = "unknown"
    raised: int = 0      # raises after it had held its target (something lowered it)
    held: bool = False   # it has read at its target since it was found
    last_raised: float | None = None
    last_warned: float | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


_lock = threading.Lock()
_tracked: dict[int, _Tracked] = {}
_thread: threading.Thread | None = None
_stop = threading.Event()
_last_discover = 0.0
_checked_at: float | None = None


def enabled() -> bool:
    return os.name == "nt" and os.environ.get(PROCESS_PRIORITY_ENV, "1").strip() != "0"


def _ibc_ancestors(gateway_pid: int, procs: list, command_line) -> list[Any]:
    """IBC's launch chain above the Gateway, by command line, oldest last; never past a pid reused later."""
    from winapi import processes

    by_pid = {p.pid: p for p in procs}
    chain: list[Any] = []
    child = by_pid.get(gateway_pid)
    child_started = processes.created_at(gateway_pid)
    for _ in range(PROCESS_PRIORITY_IBC_MAX_DEPTH):
        if child is None:
            break
        parent = by_pid.get(child.ppid)
        if parent is None:
            break
        started = processes.created_at(parent.pid)
        if started is None or child_started is None or started > child_started:
            break                                   # a pid reused after the child started is not its parent
        if not _IBC.search(command_line(parent.pid) or ""):
            break
        chain.append(parent)
        child, child_started = parent, started
    return chain


def _discover() -> list[_Tracked]:
    """The API, the IB Gateway processes and IBC's launch loop above them."""
    from ibkr import gateway_process
    from winapi import priority as pr
    from winapi import processes

    found = [_Tracked("api", os.getpid(), "api", pr.ABOVE_NORMAL, unthrottle=True)]
    try:
        procs = processes.snapshot()
    except OSError:
        logger.warning("process priority: the process list could not be read", exc_info=True)
        return found
    names = {p.pid: p.name for p in procs}
    for gw in gateway_process.find_gateways(procs, processes.command_line):
        found.append(_Tracked("gateway", gw, names.get(gw, "?"), pr.ABOVE_NORMAL))
        for parent in _ibc_ancestors(gw, procs, processes.command_line):
            found.append(_Tracked("ibc_loop", parent.pid, parent.name, pr.NORMAL))
    return found


def _low(now_priority, target: int) -> bool:
    from winapi import priority as pr

    return (
        pr.below(now_priority.cpu, target)
        or (now_priority.io is not None and now_priority.io < pr.IO_NORMAL)
        or (now_priority.memory is not None and now_priority.memory < pr.MEMORY_NORMAL)
    )


def _check(item: _Tracked, now: float) -> bool:
    """Read one process and raise it when lower than its target. False when it has exited."""
    from winapi import priority as pr

    before = pr.read(item.pid)
    if before is None:
        return item.role == "api"                      # gone (or unreadable): stop tracking it
    if not _low(before, item.target):
        item.priority, item.held, item.error = before.cpu_name, True, None
        return True
    refused = pr.raise_to(item.pid, item.target, power_unthrottle=item.unthrottle)
    after = pr.read(item.pid)
    item.priority = after.cpu_name if after is not None else "unknown"
    item.error = "; ".join(refused) or None
    if item.held:
        # It held its target before and reads lower now: something on the PC lowered it.
        item.raised += 1
        item.last_raised = now
        if item.last_warned is None or now - item.last_warned >= PROCESS_PRIORITY_WARN_EVERY_SEC:
            item.last_warned = now
            logger.warning(
                "process priority: %s (pid %s, %s) was lowered to CPU %s by something on this PC; raised "
                "to %s (%d times since Nova found it)%s", item.role, item.pid, item.name, before.cpu_name,
                item.priority, item.raised, f"; Windows refused {item.error}" if item.error else "",
            )
    else:
        logger.info("process priority: %s (pid %s, %s) CPU %s -> %s%s", item.role, item.pid, item.name,
                    before.cpu_name, item.priority, f"; Windows refused {item.error}" if item.error else "")
    item.held = after is not None and not _low(after, item.target)
    return True


def check_once(now: float | None = None) -> None:
    """One pass: look for the Gateway again when due, then read and raise every tracked process."""
    global _last_discover, _checked_at
    t = time.monotonic() if now is None else now
    if not _tracked or t - _last_discover >= PROCESS_PRIORITY_DISCOVER_SEC:
        found = _discover()
        with _lock:
            fresh = {item.pid: _tracked.get(item.pid, item) for item in found}
            _tracked.clear()
            _tracked.update(fresh)
        _last_discover = t
    with _lock:
        items = list(_tracked.values())
    gone = [item.pid for item in items if not _check(item, time.time())]
    with _lock:
        for pid in gone:
            _tracked.pop(pid, None)
    _checked_at = time.time()


def _run() -> None:
    while not _stop.is_set():
        try:
            check_once()
        except Exception:
            logger.exception("process priority: check failed")
        _stop.wait(PROCESS_PRIORITY_RECHECK_SEC)


def start() -> bool:
    """Start the ``nova-priority`` thread (Windows, unless ``NOVA_PROCESS_PRIORITY=0``)."""
    global _thread
    if not enabled():
        return False
    if _thread is not None and _thread.is_alive():
        return True
    _stop.clear()
    _thread = threading.Thread(target=_run, name="nova-priority", daemon=True)
    _thread.start()
    return True


def stop(timeout: float = 2.0) -> None:
    global _thread
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=timeout)
    _thread = None


def raise_current_thread(label: str) -> None:
    """Raise the calling thread (an event loop's) to Above Normal within the process."""
    if not enabled():
        return
    try:
        from winapi import priority as pr

        if not pr.raise_current_thread():
            logger.warning("process priority: the %s thread could not be raised", label)
    except Exception:
        logger.exception("process priority: the %s thread could not be raised", label)


def view() -> dict[str, Any]:
    """The ``process_priority`` checklist row's evidence."""
    with _lock:
        items = [
            {"role": i.role, "pid": i.pid, "name": i.name, "priority": i.priority, "raised": i.raised,
             "last_raised": i.last_raised, "error": i.error}
            for i in _tracked.values()
        ]
    return {"enabled": enabled(), "running": _thread is not None and _thread.is_alive(),
            "checked_at": _checked_at, "processes": items}


def reset_for_tests() -> None:
    global _last_discover, _checked_at
    stop()
    with _lock:
        _tracked.clear()
    _last_discover = 0.0
    _checked_at = None
