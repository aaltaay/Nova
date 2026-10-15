"""Today's warnings and trips per account, kept across a restart (ADR 056).

The file ``loss-limit-state.json`` in the operator cache (``architecture/schema/loss-limit.md``):
``{schema_version: 1, day: "YYYY-MM-DD", accounts: {ACCOUNT: {warned_at, warned_loss, tripped_at,
tripped_loss, limit_usd, sell, sold, sell_error}}}`` (``sell``: ``pending`` | ``done``, Auto sell only). Owner: this module. Invalidation: a file from an
earlier desk day (04:00 ET, ``practice.clock``) reads empty; any change to the setting clears today's
records (``clear``). An unreadable file or an unknown version reads as no trip -- logged and stated
in ``error`` -- because the watcher reads the loss again within a second and trips again if it is
still past the line; the lock is never assumed from a file Nova cannot read.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from constants_loss_limit import LOSS_LIMIT_ACCOUNTS, LOSS_LIMIT_STATE_FILE, LOSS_LIMIT_STATE_SCHEMA_VERSION

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_loaded_from: Path | None = None
_doc: dict[str, Any] = {"day": None, "accounts": {}}
_error: str | None = None


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / LOSS_LIMIT_STATE_FILE


def desk_day(ts: float) -> tuple[str, float]:
    """The desk day at ``ts`` (it turns at 04:00 ET) and the epoch second the next one begins."""
    from practice.clock import at, day_start_ts

    start = at(day_start_ts(ts))
    return start.date().isoformat(), (start + timedelta(days=1)).timestamp()


def _read(at: Path) -> tuple[dict[str, Any], str | None]:
    empty: dict[str, Any] = {"day": None, "accounts": {}}
    try:
        doc = json.loads(at.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty, None
    except (OSError, ValueError) as exc:
        logger.warning("LOSS LIMIT: %s is unreadable -- no trip is read from it", at, exc_info=True)
        return empty, f"Nova could not read today's loss limit record ({type(exc).__name__})"
    if not isinstance(doc, dict) or doc.get("schema_version") != LOSS_LIMIT_STATE_SCHEMA_VERSION:
        version = doc.get("schema_version") if isinstance(doc, dict) else None
        logger.warning("LOSS LIMIT: %s has schema_version %s -- no trip is read from it", at, version)
        return empty, f"Today's loss limit record is version {version}; this Nova reads version 1"
    accounts = doc.get("accounts")
    clean = {k: dict(v) for k, v in (accounts or {}).items() if k in LOSS_LIMIT_ACCOUNTS and isinstance(v, dict)}
    return {"day": doc.get("day") if isinstance(doc.get("day"), str) else None, "accounts": clean}, None


def _ensure(now: float) -> None:
    global _loaded_from, _doc, _error
    target = path()
    if _loaded_from != target:
        doc, error = _read(target)
        with _lock:
            _loaded_from, _doc, _error = target, doc, error
    today = desk_day(now)[0]
    if _doc.get("day") != today:
        with _lock:
            _doc = {"day": today, "accounts": {}}


def _save() -> None:
    from capture.manifest_io import write_json_atomic

    try:
        write_json_atomic(path(), {"schema_version": LOSS_LIMIT_STATE_SCHEMA_VERSION, **_doc})
    except OSError:
        # The record stays in memory for this process; a restart reads the loss again and trips again.
        logger.exception("LOSS LIMIT: today's record could not be saved -- it holds for this process only")


def record(account: str, now: float | None = None) -> dict[str, Any]:
    """``account``'s record for today (empty when nothing happened)."""
    ts = time.time() if now is None else float(now)
    _ensure(ts)
    return dict(_doc["accounts"].get(account) or {})


def records(now: float | None = None) -> tuple[str, dict[str, dict[str, Any]], str | None]:
    """``(day, {account: record}, error)``."""
    ts = time.time() if now is None else float(now)
    _ensure(ts)
    return _doc["day"], {k: dict(v) for k, v in _doc["accounts"].items()}, _error


def write(account: str, fields: dict[str, Any], now: float | None = None) -> dict[str, Any]:
    ts = time.time() if now is None else float(now)
    _ensure(ts)
    with _lock:
        row = _doc["accounts"].setdefault(account, {})
        row.update(fields)
        out = dict(row)
    _save()
    return out


def clear(now: float | None = None) -> None:
    """Every account's warning and trip for today: the setting changed, so the watcher reads afresh."""
    global _error
    ts = time.time() if now is None else float(now)
    _ensure(ts)
    with _lock:
        _doc["accounts"] = {}
        _error = None
    _save()


def until(now: float | None = None) -> float:
    """The epoch second today's records end: the next 04:00 ET."""
    return desk_day(time.time() if now is None else float(now))[1]


def reset_for_tests() -> None:
    global _loaded_from, _doc, _error
    with _lock:
        _loaded_from, _doc, _error = None, {"day": None, "accounts": {}}, None
