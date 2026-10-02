"""Is an IB Gateway (or TWS) process running on this PC -- one answer for every caller.

Gateway 10.45 runs as ``ibgateway1.exe``. The old check (``Get-Process -Name ibgateway,tws``)
never matched it, so ``launch_or_focus_gateway`` read "no Gateway" while one ran and started a
second: on 2026-10-02 at 12:46 that second Gateway took over the IBKR login from the first.

Owner of the process check and its short cache (``IBKR_GATEWAY_PROCESS_CACHE_SEC``): status
polls ask it, and one ``tasklist`` run is about 100 ms -- a PowerShell run was 250-935 ms on
the HTTP loop.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import subprocess
import time

from constants_ibkr import IBKR_GATEWAY_PROCESS_CACHE_SEC, IBKR_GATEWAY_PROCESS_PREFIXES

logger = logging.getLogger(__name__)

_cache: tuple[float, bool] | None = None


def reset_for_tests() -> None:
    global _cache
    _cache = None


def gateway_images(tasklist_csv: str) -> list[str]:
    """Image names in ``tasklist /FO CSV /NH`` output that are a Gateway or TWS (pure)."""
    found: list[str] = []
    for row in csv.reader(io.StringIO(tasklist_csv)):
        if not row:
            continue
        image = row[0].strip().lower()
        stem = image[:-4] if image.endswith(".exe") else image
        if any(stem == p or (stem.startswith(p) and stem[len(p):].isdigit()) for p in IBKR_GATEWAY_PROCESS_PREFIXES):
            found.append(row[0].strip())
    return found


def _tasklist() -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    done = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                          timeout=10, check=False, creationflags=flags)
    return done.stdout or ""


def running(now: float | None = None) -> bool:
    """True when a Gateway or TWS process runs. Unknown (the check failed) reads False, logged."""
    global _cache
    if os.name != "nt":
        return False
    ts = time.monotonic() if now is None else now
    if _cache is not None and ts - _cache[0] < IBKR_GATEWAY_PROCESS_CACHE_SEC:
        return _cache[1]
    try:
        answer = bool(gateway_images(_tasklist()))
    except (OSError, subprocess.SubprocessError):
        logger.warning("IBKR: could not list processes to find the Gateway", exc_info=True)
        answer = False
    _cache = (ts, answer)
    return answer
