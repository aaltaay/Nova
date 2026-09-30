"""The desktop app's newest clip view (ADR 039).

Owner: this module's in-memory state -- the last validated view and when it
arrived. Invalidation: a view older than ``CLIPS_STALE_SEC`` is not fresh (no
desktop app is reporting); a restart forgets it until the app's next report.
Not persisted; the wire's schema_version is ``CLIPS_SCHEMA_VERSION``.
"""
from __future__ import annotations

import threading
import time
from typing import Any

from constants_clips import CLIPS_SCHEMA_VERSION, CLIPS_STALE_SEC

_lock = threading.Lock()
_view: dict[str, Any] | None = None
_received_ts: float | None = None


def reset_for_tests() -> None:
    global _view, _received_ts
    with _lock:
        _view = None
        _received_ts = None


def record(view: dict[str, Any], *, now: float | None = None) -> None:
    """Keep one validated view."""
    global _view, _received_ts
    with _lock:
        _view = dict(view)
        _received_ts = time.time() if now is None else now


def status(now: float | None = None) -> dict[str, Any]:
    """``{schema_version, reported, fresh, age_sec, received_ts, view}`` -- view is the app's own."""
    now = time.time() if now is None else now
    with _lock:
        view = dict(_view) if _view is not None else None
        received = _received_ts
    age = None if received is None else max(0.0, now - received)
    return {
        "schema_version": CLIPS_SCHEMA_VERSION,
        "reported": view is not None,
        "fresh": age is not None and age <= CLIPS_STALE_SEC,
        "age_sec": None if age is None else round(age, 1),
        "received_ts": received,
        "view": view,
    }
