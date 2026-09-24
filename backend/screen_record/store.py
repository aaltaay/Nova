"""The desktop app's newest screen recording report (ADR 035).

Owner: this module's in-memory state -- the last validated report and when it
arrived. Invalidation: a report older than ``SCREEN_RECORD_STALE_SEC`` is not
fresh (no desktop app is reporting, so nothing says the screen is recorded); a
restart forgets it until the app's next report. Not persisted; the wire's
schema_version is ``SCREEN_RECORD_SCHEMA_VERSION``.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from constants_screen_record import SCREEN_RECORD_SCHEMA_VERSION, SCREEN_RECORD_STALE_SEC

_lock = threading.Lock()
_report: dict[str, Any] | None = None
_received_ts: float | None = None


def reset_for_tests() -> None:
    global _report, _received_ts
    with _lock:
        _report = None
        _received_ts = None


def record(report: dict[str, Any], *, now: float | None = None) -> None:
    """Keep one validated report."""
    global _report, _received_ts
    with _lock:
        _report = dict(report)
        _received_ts = time.time() if now is None else now


def status(now: float | None = None) -> dict[str, Any]:
    """``{schema_version, reported, fresh, age_sec, received_ts, report}`` -- report is the app's own view."""
    now = time.time() if now is None else now
    with _lock:
        report = dict(_report) if _report is not None else None
        received = _received_ts
    age = None if received is None else max(0.0, now - received)
    return {
        "schema_version": SCREEN_RECORD_SCHEMA_VERSION,
        "reported": report is not None,
        "fresh": age is not None and age <= SCREEN_RECORD_STALE_SEC,
        "age_sec": None if age is None else round(age, 1),
        "received_ts": received,
        "report": report,
    }
