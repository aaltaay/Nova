"""Did the PC's Wi-Fi drop? Windows' WLAN AutoConfig log over a stretch of time (#672).

Owner: this module. Read-only -- it queries the event log with ``wevtutil`` and
never writes anything.

Why (2026-10-01): at the open the desk's charts and Time & Sales stopped for 4 to
16 seconds at a time. Each silence matched, to the second, a Wi-Fi
re-authentication Windows logged -- 11004 "Wireless security stopped" then 11005
"Wireless security succeeded" -- while Nova and IB Gateway kept running. Naming
the drop on the desk tells the operator where to look (a cable, not Nova).

Never waits on a loop: ``lookup`` answers from memory and asks one worker thread
to read the log (``wevtutil`` takes ~0.1 s). A log that cannot be read is
``unknown`` -- never "no drop" -- and off Windows the answer is ``off``.
"""
from __future__ import annotations

import logging
import queue
import subprocess
import sys
import threading
import time
from typing import Any

from constants_feed import (
    WIFI_CACHE_KEEP,
    WIFI_EVENT_SECURITY_STOPPED,
    WIFI_EVENT_SECURITY_SUCCEEDED,
    WIFI_LOG,
    WIFI_LOOKBACK_SEC,
    WIFI_REREAD_SEC,
    WIFI_WEVTUTIL_MAX_EVENTS,
    WIFI_WEVTUTIL_TIMEOUT_SEC,
)
from ibkr.windows_restarts import parse_events_xml

logger = logging.getLogger(__name__)

STATE_READ = "read"
STATE_PENDING = "pending"
STATE_UNKNOWN = "unknown"
STATE_OFF = "off"


def drops_from_events(events: list[dict[str, Any]]) -> list[dict[str, float | None]]:
    """Pure: each 11004 paired with the next 11005, oldest first.

    ``stopped`` is ``None`` when the log shows the link coming back without the
    drop that preceded it (read from before the window); ``back`` is ``None``
    while the link has not come back."""
    out: list[dict[str, float | None]] = []
    stopped: float | None = None
    for ev in sorted(events, key=lambda e: e["ts"]):
        if ev["id"] == WIFI_EVENT_SECURITY_STOPPED:
            if stopped is None:
                stopped = ev["ts"]
        elif ev["id"] == WIFI_EVENT_SECURITY_SUCCEEDED:
            out.append({"stopped": stopped, "back": ev["ts"]})
            stopped = None
    if stopped is not None:
        out.append({"stopped": stopped, "back": None})
    return out


def overlapping(drops: list[dict[str, float | None]], start: float, end: float) -> list[dict[str, float | None]]:
    """Pure: the drops down at any moment from ``WIFI_LOOKBACK_SEC`` before ``start`` to ``end``."""
    lo = start - WIFI_LOOKBACK_SEC
    hits = []
    for d in drops:
        down = d.get("stopped")
        up = d.get("back")
        if (down is None or down <= end) and (up is None or up >= lo):
            hits.append(d)
    return hits


def _query(window_sec: float) -> str | None:
    if sys.platform != "win32":
        return None
    ids = f"EventID={WIFI_EVENT_SECURITY_STOPPED} or EventID={WIFI_EVENT_SECURITY_SUCCEEDED}"
    query = f"*[System[({ids}) and TimeCreated[timediff(@SystemTime) <= {int(window_sec * 1000)}]]]"
    try:
        done = subprocess.run(
            ["wevtutil", "qe", WIFI_LOG, f"/q:{query}", f"/c:{WIFI_WEVTUTIL_MAX_EVENTS}", "/rd:true", "/f:xml"],
            capture_output=True,
            text=True,
            timeout=WIFI_WEVTUTIL_TIMEOUT_SEC,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        logger.warning("wifi_drops: wevtutil failed", exc_info=True)
        return None
    if done.returncode != 0:
        logger.warning("wifi_drops: wevtutil exit %s: %s", done.returncode, (done.stderr or "").strip()[:200])
        return None
    return done.stdout


def read_drops(start: float, end: float, now: float | None = None) -> list[dict[str, float | None]] | None:
    """The Wi-Fi drops logged from ``WIFI_LOOKBACK_SEC`` before ``start`` to ``end``;
    ``None`` when the log cannot be read."""
    t = time.time() if now is None else now
    text = _query(max(0.0, t - start) + WIFI_LOOKBACK_SEC + 1.0)
    events = parse_events_xml(text) if text is not None else None
    if events is None:
        return None
    return overlapping(drops_from_events(events), start, end)


_lock = threading.Lock()
_cache: dict[float, dict[str, Any]] = {}
_pending: set[float] = set()
_queue: queue.SimpleQueue = queue.SimpleQueue()
_worker: threading.Thread | None = None


def lookup(start: float, end: float | None, now: float | None = None) -> dict[str, Any]:
    """``{state, drops}`` for the stretch from ``start`` to ``end`` (``None``: still open), from
    memory. Asks the worker to read the log when nothing is kept for this stretch, when it
    ended since the last read, or every ``WIFI_REREAD_SEC`` while it is open."""
    if sys.platform != "win32":
        return {"state": STATE_OFF, "drops": []}
    t = time.time() if now is None else now
    with _lock:
        got = _cache.get(start)
        stale = (got is None or got["end"] != end
                 or (end is None and t - got["read_at"] >= WIFI_REREAD_SEC))
        if stale and start not in _pending:
            _pending.add(start)
            _queue.put((start, end))
            _ensure_worker()
    if got is None:
        return {"state": STATE_PENDING, "drops": []}
    return {"state": got["state"], "drops": list(got["drops"])}


def _ensure_worker() -> None:
    """Caller holds ``_lock``."""
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_work, name="wifi-drops", daemon=True)
        _worker.start()


def _work() -> None:
    while True:
        start, end = _queue.get()
        try:
            stop = end if end is not None else time.time()
            drops = read_drops(start, stop)
        except Exception:
            logger.warning("wifi_drops: reading the Wi-Fi log failed", exc_info=True)
            drops = None
        with _lock:
            _cache[start] = {
                "end": end,
                "read_at": time.time(),
                "state": STATE_READ if drops is not None else STATE_UNKNOWN,
                "drops": drops or [],
            }
            _pending.discard(start)
            while len(_cache) > WIFI_CACHE_KEEP:
                _cache.pop(min(_cache))


def _reset_for_tests() -> None:
    with _lock:
        _cache.clear()
        _pending.clear()
