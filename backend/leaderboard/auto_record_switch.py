"""The operator's auto-record switch: On, Off for today, Off (operator ask 2026-10-14).

Operator, 2026-10-14: "i need a way to turn off the recording". The two recordings on screen
were auto-record's -- the 5-minute flat top's arming window runs to 15:30 ET -- and the only off
switch was ``NOVA_AUTO_RECORD=0`` in ``.env`` plus a restart.

The file ``auto-record-switch.json`` in the operator cache (``architecture/schema/scanner.md``,
Auto-record): ``{schema_version: 1, mode: "on" | "off_today" | "off", day: "YYYY-MM-DD" | null,
set_at: epoch}``. Owner: this module. Invalidation: rewritten on every change; ``off_today``
reads as ``on`` once the desk day (from 04:00 ET, ``practice.clock.day_start_ts``) is past
``day``. No file is ``on`` -- what auto-record did before the switch existed. An unknown version
or an unreadable file reads as ``on``, logged and stated in ``error``, never a silent guess.

``NOVA_AUTO_RECORD=0`` still holds it off whatever the file says (``source: "env"``): the switch
never overrides ``.env``.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AUTO_RECORD_ENV = "NOVA_AUTO_RECORD"
AUTO_RECORD_SWITCH_FILE = "auto-record-switch.json"
AUTO_RECORD_SWITCH_SCHEMA_VERSION = 1

MODE_ON, MODE_OFF_TODAY, MODE_OFF = "on", "off_today", "off"
MODES = (MODE_ON, MODE_OFF_TODAY, MODE_OFF)
SOURCE_OPERATOR, SOURCE_ENV, SOURCE_DEFAULT = "operator", "env", "default"

ENV_HOLDS_OFF = (f"{AUTO_RECORD_ENV}=0 in .env keeps auto-record off -- remove that line and restart Nova "
                 "to use this switch")


class EnvHoldsOff(RuntimeError):
    """``.env`` holds auto-record off: the switch cannot change it."""


_lock = threading.Lock()
_loaded_from: Path | None = None        # the file the memory below was read from
_saved: dict[str, Any] | None = None    # {mode, day, set_at}; None with no file (or one it cannot read)
_error: str | None = None


def env_off() -> bool:
    return (os.environ.get(AUTO_RECORD_ENV) or "1").strip().lower() in ("0", "false", "off", "no")


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / AUTO_RECORD_SWITCH_FILE


def desk_day(ts: float) -> tuple[str, float]:
    """The desk day at ``ts`` (it turns at 04:00 ET) and the epoch second the next one begins."""
    from practice.clock import at, day_start_ts

    start = at(day_start_ts(ts))
    return start.date().isoformat(), (start + timedelta(days=1)).timestamp()


def read(at: Path) -> tuple[dict[str, Any] | None, str | None]:
    """``(saved, error)``: ``(None, None)`` with no file; ``(None, why)`` for one this build cannot use."""
    try:
        doc = json.loads(at.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        logger.warning("AUTO-RECORD: %s is unreadable -- the switch reads On", at, exc_info=True)
        return None, f"Nova could not read the saved switch ({type(exc).__name__}), so auto-record is on"
    version = doc.get("schema_version") if isinstance(doc, dict) else None
    if version != AUTO_RECORD_SWITCH_SCHEMA_VERSION:
        logger.warning("AUTO-RECORD: %s has schema_version %s; this build reads %s -- the switch reads On",
                       at, version, AUTO_RECORD_SWITCH_SCHEMA_VERSION)
        return None, (f"The saved switch is version {version}; this Nova reads version "
                      f"{AUTO_RECORD_SWITCH_SCHEMA_VERSION}, so auto-record is on")
    mode = doc.get("mode")
    if mode not in MODES:
        logger.warning("AUTO-RECORD: %s names mode %r -- the switch reads On", at, mode)
        return None, f"The saved switch names an unknown setting ({mode!r}), so auto-record is on"
    day = doc.get("day")
    set_at = doc.get("set_at")
    return {"mode": mode, "day": day if isinstance(day, str) else None,
            "set_at": float(set_at) if isinstance(set_at, (int, float)) else None}, None


def ensure_loaded() -> None:
    """Read the file once per cache folder (blocking: the tick calls it off the loop first)."""
    global _loaded_from, _saved, _error
    target = path()
    if _loaded_from == target:
        return
    saved, error = read(target)
    with _lock:
        _loaded_from, _saved, _error = target, saved, error


def state(now: float | None = None) -> dict[str, Any]:
    """``{mode, source, day, until, error}`` -- what the switch says at ``now``."""
    ts = time.time() if now is None else float(now)
    if env_off():
        return {"mode": MODE_OFF, "source": SOURCE_ENV, "day": None, "until": None, "error": None}
    ensure_loaded()
    saved, error = _saved, _error
    if saved is None:
        return {"mode": MODE_ON, "source": SOURCE_DEFAULT, "day": None, "until": None, "error": error}
    if saved["mode"] == MODE_OFF_TODAY:
        today, next_day = desk_day(ts)
        if saved["day"] != today:
            # Off for a desk day that has passed: on again from its 04:00 ET.
            return {"mode": MODE_ON, "source": SOURCE_DEFAULT, "day": None, "until": None, "error": None}
        return {"mode": MODE_OFF_TODAY, "source": SOURCE_OPERATOR, "day": today, "until": next_day, "error": None}
    return {"mode": saved["mode"], "source": SOURCE_OPERATOR, "day": None, "until": None, "error": None}


def is_on(now: float | None = None) -> bool:
    return state(now)["mode"] == MODE_ON


def set_mode(mode: str, now: float | None = None) -> dict[str, Any]:
    """Save the operator's choice and answer the new ``state`` (blocking: call it off the loop).

    ``EnvHoldsOff`` while ``.env`` holds it off; ``ValueError`` for an unknown mode; ``OSError``
    when the file cannot be written -- the switch is then unchanged."""
    global _loaded_from, _saved, _error
    if mode not in MODES:
        raise ValueError(f"unknown auto-record setting {mode!r}; one of {', '.join(MODES)}")
    if env_off():
        raise EnvHoldsOff(ENV_HOLDS_OFF)
    from capture.manifest_io import write_json_atomic

    ts = time.time() if now is None else float(now)
    day = desk_day(ts)[0] if mode == MODE_OFF_TODAY else None
    target = path()
    write_json_atomic(target, {"schema_version": AUTO_RECORD_SWITCH_SCHEMA_VERSION, "mode": mode, "day": day,
                               "set_at": ts})
    with _lock:
        _loaded_from, _saved, _error = target, {"mode": mode, "day": day, "set_at": ts}, None
    logger.info("AUTO-RECORD: the operator set auto-record to %s", mode)
    return state(ts)


def reset_for_tests() -> None:
    global _loaded_from, _saved, _error
    with _lock:
        _loaded_from, _saved, _error = None, None, None
