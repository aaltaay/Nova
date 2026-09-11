"""Durable kill-switch latch (D-037).

Owner
    ``strategy.executor`` — the only module that reads or writes this file.

Invalidation trigger
    An explicit ``executor.reset_kill_switch()`` and nothing else. A tripped
    kill deliberately survives process restart: "restart clears kill" is how an
    operator who killed the desk came back to an armed desk.

schema_version
    ``KILL_SWITCH_STATE_SCHEMA_VERSION``. An unknown version refuses loud and
    fails **tripped** — a latch we cannot read is never assumed to be clear.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from constants import (
    KILL_SWITCH_STATE_FILENAME,
    KILL_SWITCH_STATE_SCHEMA_VERSION,
)
from paths import cache_dir

logger = logging.getLogger(__name__)


def _path() -> Path:
    return cache_dir() / KILL_SWITCH_STATE_FILENAME


def load() -> dict:
    """Return ``{"tripped", "reason", "ts"}``; unreadable state fails tripped."""
    path = _path()
    if not path.exists():
        return {"tripped": False, "reason": None, "ts": None}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception(
            "kill switch: %s unreadable — failing tripped until reset", path.name,
        )
        return {"tripped": True, "reason": "state_file_unreadable", "ts": None}
    version = raw.get("schema_version") if isinstance(raw, dict) else None
    if version != KILL_SWITCH_STATE_SCHEMA_VERSION:
        logger.error(
            "kill switch: %s schema_version=%r (expected %s) — failing tripped",
            path.name, version, KILL_SWITCH_STATE_SCHEMA_VERSION,
        )
        return {"tripped": True, "reason": "state_schema_unknown", "ts": None}
    return {
        "tripped": bool(raw.get("tripped")),
        "reason": raw.get("reason"),
        "ts": raw.get("ts"),
    }


def save(*, tripped: bool, reason: str | None) -> None:
    """Persist the latch. A failed write is loud — never silently in-memory."""
    payload = {
        "schema_version": KILL_SWITCH_STATE_SCHEMA_VERSION,
        "tripped": bool(tripped),
        "reason": reason,
        "ts": time.time(),
    }
    try:
        _path().write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        logger.exception(
            "kill switch: could not persist tripped=%s — a restart will not "
            "remember this latch",
            tripped,
        )
