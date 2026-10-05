"""Is an IB Gateway (or TWS) process running on this PC -- one answer for every caller.

Gateway 10.45 started by its own launcher runs as ``ibgateway1.exe``; the old check
(``Get-Process -Name ibgateway,tws``) never matched it, so ``launch_or_focus_gateway`` read "no
Gateway" while one ran and started a second: on 2026-10-02 at 12:46 that second Gateway took over
the IBKR login from the first. Started by IBC -- the desk's way -- the Gateway runs as the bundled
``java.exe`` running ``ibcalpha.ibc.IbcGateway``, which an image-name check misses too (2026-10-05).

Owner of the process check and its short cache (``IBKR_GATEWAY_PROCESS_CACHE_SEC``). The process
list is read in-process (``winapi.processes``, tens of ms, no subprocess): a ``tasklist`` run held
the socket loop 0.1-1.7 s, 1,047 times on 2026-10-05 (536 s). A java process's command line is
only matched against markers here, never logged -- IBC's carries its encrypted credentials.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Callable, Iterable

from constants_ibkr import IBKR_GATEWAY_PROCESS_CACHE_SEC, IBKR_GATEWAY_PROCESS_PREFIXES

logger = logging.getLogger(__name__)

# A java process is a Gateway or TWS when its command line names one of these (IBC's main class,
# the Gateway's or TWS's install folders and launcher jars).
_JAVA_IMAGES = ("java.exe", "javaw.exe")
_JAVA_MARKERS = re.compile(r"ibcalpha\.ibc\.|[\\/]ibgateway[\\/]|jts4launch|twslaunch", re.IGNORECASE)

_lock = threading.Lock()
_cache: tuple[float, tuple[int, ...]] | None = None


def reset_for_tests() -> None:
    global _cache
    with _lock:
        _cache = None


def is_gateway_image(image: str) -> bool:
    """An ``ibgateway*`` / ``tws*`` image name (``ibgateway1.exe`` included) -- pure."""
    name = image.strip().lower()
    stem = name[:-4] if name.endswith(".exe") else name
    return any(stem == p or (stem.startswith(p) and stem[len(p):].isdigit()) for p in IBKR_GATEWAY_PROCESS_PREFIXES)


def is_gateway_java(image: str, command_line: str | None) -> bool:
    """A java process running IB Gateway or TWS (IBC's launch included) -- pure."""
    return image.strip().lower() in _JAVA_IMAGES and bool(command_line) and bool(_JAVA_MARKERS.search(command_line))


def find_gateways(procs: Iterable, command_line: Callable[[int], str | None]) -> list[int]:
    """The pids of every Gateway / TWS process in ``procs`` (``.pid``, ``.name``) -- pure but for the reader."""
    found: list[int] = []
    for proc in procs:
        if is_gateway_image(proc.name):
            found.append(proc.pid)
        elif proc.name.strip().lower() in _JAVA_IMAGES and is_gateway_java(proc.name, command_line(proc.pid)):
            found.append(proc.pid)
    return found


def _read() -> tuple[int, ...]:
    from winapi import processes

    return tuple(find_gateways(processes.snapshot(), processes.command_line))


def pids(now: float | None = None) -> tuple[int, ...]:
    """The Gateway / TWS processes now (cached ``IBKR_GATEWAY_PROCESS_CACHE_SEC``). Empty off Windows,
    or when the list cannot be read (logged)."""
    global _cache
    if os.name != "nt":
        return ()
    ts = time.monotonic() if now is None else now
    with _lock:
        if _cache is not None and ts - _cache[0] < IBKR_GATEWAY_PROCESS_CACHE_SEC:
            return _cache[1]
    try:
        answer = _read()
    except OSError:
        logger.warning("IBKR: could not list processes to find the Gateway", exc_info=True)
        answer = ()
    with _lock:
        _cache = (ts, answer)
    return answer


def running(now: float | None = None) -> bool:
    """True when a Gateway or TWS process runs. Unknown (the check failed) reads False, logged."""
    return bool(pids(now))
