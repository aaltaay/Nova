"""The recent refusals, in memory, for the desk diagnostics row (#828 item 1).

A refused socket shows in a browser only as close code 1006, so the desk reads
why from here (``diagnostics/collect_request_guard.py``). The middleware feeds it
at the same call site as the log (``middleware.RefusalLog``), but it is not the
log's rate limiter: every refusal counts here, and the log's 60 s window never
hides one.

One entry per refused (kind, header, value), at most ``RECENT_REFUSALS_MAX``;
past that the least recently seen entry is dropped and counted. Module-level so
the diagnostics shell reads it without the middleware instance; one lock, since
the middleware writes on the event loop and the checklist reads on a worker.
Refused values are attacker-controlled text: stored cut, never parsed here.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

from request_guard.constants_request_guard import LOGGED_VALUE_MAX_CHARS, RECENT_REFUSALS_MAX
from request_guard.policy import Refusal

_lock = threading.Lock()
# (kind, header, value) -> entry; ordered least recently seen first.
_entries: OrderedDict[tuple[str, str, str], dict[str, Any]] = OrderedDict()
_totals = {"refused": 0, "dropped": 0}


def record(
    kind: str,
    path: str,
    refusal: Refusal,
    *,
    now: float | None = None,
    max_entries: int = RECENT_REFUSALS_MAX,
) -> None:
    """Count one refusal: ``kind`` is the ASGI scope type (``http`` or ``websocket``)."""
    ts = time.time() if now is None else float(now)
    value = refusal.value[:LOGGED_VALUE_MAX_CHARS]
    key = (kind, refusal.header, value)
    with _lock:
        _totals["refused"] += 1
        entry = _entries.get(key)
        if entry is None:
            entry = {"kind": kind, "header": refusal.header, "value": value,
                     "reason": refusal.reason, "count": 0, "first_at": ts}
            _entries[key] = entry
        else:
            _entries.move_to_end(key)
        entry["count"] += 1
        entry["last_at"] = ts
        entry["last_path"] = path[:LOGGED_VALUE_MAX_CHARS]
        while len(_entries) > max(1, max_entries):
            _entries.popitem(last=False)
            _totals["dropped"] += 1


def snapshot() -> dict[str, Any]:
    """JSON-safe copy: ``refusals`` newest first, the totals since the API started, and the cap."""
    with _lock:
        refusals = sorted((dict(entry) for entry in _entries.values()), key=lambda e: e["last_at"], reverse=True)
        totals = dict(_totals)
    return {
        "refusals": refusals,
        "refused_total": totals["refused"],
        "dropped_values": totals["dropped"],
        "max_values": RECENT_REFUSALS_MAX,
    }


def reset_for_tests() -> None:
    with _lock:
        _entries.clear()
        _totals["refused"] = 0
        _totals["dropped"] = 0
