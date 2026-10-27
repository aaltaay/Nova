"""Today's warnings and trips per account and line, kept across a restart (ADR 056, ADR 061).

The file ``loss-limit-state.json`` in the operator cache (``architecture/schema/loss-limit.md``):
``{schema_version: 2, day: "YYYY-MM-DD", accounts: {ACCOUNT: {LINE: {warned_at, warned_loss,
tripped_at, tripped_loss, limit_usd, sell, sold, sell_error}}}}`` (``LINE`` one of ``account`` /
``you`` / ``bots``; ``sell``: ``pending`` | ``done``, Auto sell only). Owner: this module.
Invalidation: a file from an earlier desk day (04:00 ET of the trading session, ``day_start``) reads empty; any change
to the setting clears today's records (``clear``). A version 1 file -- one record per account, the
one line ADR 056 had -- reads as each account's Account line, so a trip from before the upgrade
still holds. An unreadable file or an unknown version reads as no trip -- logged and stated in
``error`` -- because the watcher reads the loss again within a second and trips again if it is
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

from constants_loss_limit import (
    LOSS_LIMIT_ACCOUNTS,
    LOSS_LIMIT_LINE_ACCOUNT,
    LOSS_LIMIT_LINES,
    LOSS_LIMIT_STATE_FILE,
    LOSS_LIMIT_STATE_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

_V1 = 1
_lock = threading.Lock()
_loaded_from: Path | None = None
_doc: dict[str, Any] = {"day": None, "accounts": {}}
_error: str | None = None


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / LOSS_LIMIT_STATE_FILE


def day_start(ts: float) -> float:
    """The epoch second the desk day ``ts`` belongs to began: 04:00 ET of its trading session.

    The session is the rest of the desk's (``market.session_key_et``): a weekend or NYSE holiday belongs
    to the last exchange day before it, so a Friday's count holds until the next exchange day (#1090).
    """
    from practice.clock import session_day_start_ts

    return session_day_start_ts(ts)


def desk_day(ts: float) -> tuple[str, float]:
    """The desk day at ``ts`` and the epoch second the next one begins: the next exchange day's 04:00 ET."""
    from market import next_exchange_day
    from practice.clock import at

    start = at(day_start(ts))
    after = next_exchange_day(start.date())
    # Same wall clock on the later date: 04:00 ET in either offset across a DST weekend.
    return start.date().isoformat(), (start + timedelta(days=(after - start.date()).days)).timestamp()


def _lines(row: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(row, dict):
        return {}
    return {line: dict(rec) for line, rec in row.items() if line in LOSS_LIMIT_LINES and isinstance(rec, dict)}


def _read(at: Path) -> tuple[dict[str, Any], str | None]:
    empty: dict[str, Any] = {"day": None, "accounts": {}}
    try:
        doc = json.loads(at.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty, None
    except (OSError, ValueError) as exc:
        logger.warning("LOSS LIMIT: %s is unreadable -- no trip is read from it", at, exc_info=True)
        return empty, f"Nova could not read today's loss limit record ({type(exc).__name__})"
    version = doc.get("schema_version") if isinstance(doc, dict) else None
    if version not in (_V1, LOSS_LIMIT_STATE_SCHEMA_VERSION):
        logger.warning("LOSS LIMIT: %s has schema_version %s -- no trip is read from it", at, version)
        return empty, (f"Today's loss limit record is version {version}; this Nova reads version "
                       f"{LOSS_LIMIT_STATE_SCHEMA_VERSION}")
    accounts = doc.get("accounts") if isinstance(doc.get("accounts"), dict) else {}
    clean: dict[str, dict[str, dict[str, Any]]] = {}
    for account, row in accounts.items():
        if account not in LOSS_LIMIT_ACCOUNTS or not isinstance(row, dict):
            continue
        # Version 1 kept one record per account: ADR 056's one line, now the Account line.
        clean[account] = {LOSS_LIMIT_LINE_ACCOUNT: dict(row)} if version == _V1 else _lines(row)
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


def record(account: str, now: float | None = None, *, line: str = LOSS_LIMIT_LINE_ACCOUNT) -> dict[str, Any]:
    """``account``'s record for ``line`` today (empty when nothing happened)."""
    ts = time.time() if now is None else float(now)
    _ensure(ts)
    return dict((_doc["accounts"].get(account) or {}).get(line) or {})


def records(now: float | None = None) -> tuple[str, dict[str, dict[str, dict[str, Any]]], str | None]:
    """``(day, {account: {line: record}}, error)``."""
    ts = time.time() if now is None else float(now)
    _ensure(ts)
    return _doc["day"], {k: {line: dict(rec) for line, rec in v.items()} for k, v in _doc["accounts"].items()}, _error


def write(account: str, fields: dict[str, Any], now: float | None = None, *,
          line: str = LOSS_LIMIT_LINE_ACCOUNT) -> dict[str, Any]:
    ts = time.time() if now is None else float(now)
    _ensure(ts)
    with _lock:
        row = _doc["accounts"].setdefault(account, {}).setdefault(line, {})
        row.update(fields)
        out = dict(row)
    _save()
    return out


def clear(now: float | None = None) -> None:
    """Every account's warnings and trips for today: the setting changed, so the watcher reads afresh."""
    global _error
    ts = time.time() if now is None else float(now)
    _ensure(ts)
    with _lock:
        _doc["accounts"] = {}
        _error = None
    _save()


def until(now: float | None = None) -> float:
    """The epoch second today's records end: the next exchange day's 04:00 ET."""
    return desk_day(time.time() if now is None else float(now))[1]


def reset_for_tests() -> None:
    global _loaded_from, _doc, _error
    with _lock:
        _loaded_from, _doc, _error = None, {"day": None, "accounts": {}}, None
