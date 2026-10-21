"""The operator's order size limit setting: Max shares and Max risk at stop, per practice venue (ADR 064).

The file ``order-size-limit.json`` in the operator cache (``architecture/schema/execution.md``):
``{schema_version: 1, venues: {paper: {max_shares, max_risk_usd}, sim: {...}}, set_at}``, each number a
whole number or null (no limit). Owner: this module. Invalidation: rewritten whole on every change.
No file means every limit is off. A file this build cannot use -- unreadable, another version, a value
out of its rule -- is not read as off: ``current()`` says ``source: "unreadable"`` with the reason in
``error``, and the door refuses new hand orders on Paper and Sim until the next save writes a fresh file.
A limit that silently vanished would be the one the operator trusted.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from pathlib import Path
from typing import Any

from constants_order_size_limit import (
    ORDER_SIZE_LIMIT_FIELDS,
    ORDER_SIZE_LIMIT_FILE,
    ORDER_SIZE_LIMIT_MAX_RISK_USD,
    ORDER_SIZE_LIMIT_MAX_SHARES,
    ORDER_SIZE_LIMIT_MIN_RISK_USD,
    ORDER_SIZE_LIMIT_MIN_SHARES,
    ORDER_SIZE_LIMIT_SCHEMA_VERSION,
    ORDER_SIZE_LIMIT_VENUES,
)

logger = logging.getLogger(__name__)

_NAMES = {"max_shares": "Max shares", "max_risk_usd": "Max risk at stop"}

_lock = threading.Lock()
# One save at a time: each reads the setting, changes it and writes the file whole, so two at once would both
# start from the same old setting and the second would drop the first's change (and share one temp file).
_save_lock = threading.Lock()
_loaded_from: Path | None = None
_saved: dict[str, Any] | None = None    # None with no file, or one this build cannot use
_error: str | None = None


class Invalid(ValueError):
    """A change this setting refuses; the message says the rule."""


def defaults() -> dict[str, dict[str, int | None]]:
    """Every limit off: no number in Nova's code (operator decision 2026-10-20)."""
    return {venue: {field: None for field in ORDER_SIZE_LIMIT_FIELDS} for venue in ORDER_SIZE_LIMIT_VENUES}


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / ORDER_SIZE_LIMIT_FILE


def _problem(field: str, value: Any) -> str | None:
    """Why ``value`` is not a ``field`` number, or None. Null is always fine: no limit."""
    if value is None:
        return None
    if field == "max_shares":
        low, high, unit = ORDER_SIZE_LIMIT_MIN_SHARES, ORDER_SIZE_LIMIT_MAX_SHARES, "shares"
    else:
        low, high, unit = ORDER_SIZE_LIMIT_MIN_RISK_USD, ORDER_SIZE_LIMIT_MAX_RISK_USD, "dollars"
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value):
        return f"{_NAMES[field]} is whole {unit}, or empty for no limit"
    if not low <= value <= high:
        bounds = f"{low:,} to {high:,}" if unit == "shares" else f"${low:,} to ${high:,}"
        return f"{_NAMES[field]} is {bounds}, or empty for no limit"
    return None


def read(at: Path) -> tuple[dict[str, Any] | None, str | None]:
    """``(saved, error)``: ``(None, None)`` with no file; ``(None, why)`` for one this build cannot use."""
    try:
        doc = json.loads(at.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        logger.warning("ORDER SIZE LIMIT: %s is unreadable", at, exc_info=True)
        return None, f"Nova could not read the saved order size limit ({type(exc).__name__})"
    version = doc.get("schema_version") if isinstance(doc, dict) else None
    if version != ORDER_SIZE_LIMIT_SCHEMA_VERSION:
        logger.warning("ORDER SIZE LIMIT: %s has schema_version %s; this build reads %s",
                       at, version, ORDER_SIZE_LIMIT_SCHEMA_VERSION)
        return None, (f"The saved order size limit is version {version}; this Nova reads version "
                      f"{ORDER_SIZE_LIMIT_SCHEMA_VERSION}")
    venues = doc.get("venues")
    if not isinstance(venues, dict) or any(not isinstance(venues.get(v, {}), dict) for v in ORDER_SIZE_LIMIT_VENUES):
        logger.warning("ORDER SIZE LIMIT: %s has no venues this build can read", at)
        return None, "The saved order size limit holds no venues Nova can read"
    out = defaults()
    for venue in ORDER_SIZE_LIMIT_VENUES:
        row = venues.get(venue, {})
        for field in ORDER_SIZE_LIMIT_FIELDS:
            value = row.get(field)
            if _problem(field, value):
                logger.warning("ORDER SIZE LIMIT: %s holds %s=%r for %s", at, field, value, venue)
                return None, "The saved order size limit holds a value Nova cannot use"
            out[venue][field] = None if value is None else int(value)
    set_at = doc.get("set_at")
    return {"venues": out, "set_at": float(set_at) if isinstance(set_at, (int, float)) else None}, None


def ensure_loaded() -> None:
    global _loaded_from, _saved, _error
    target = path()
    if _loaded_from == target:
        return
    saved, error = read(target)
    with _lock:
        _loaded_from, _saved, _error = target, saved, error


def current() -> dict[str, Any]:
    """``{venues, set_at, source, error}``; ``source`` is ``default`` (no file), ``operator`` or ``unreadable``."""
    ensure_loaded()
    saved, error = _saved, _error
    if saved is None:
        return {"venues": defaults(), "set_at": None, "source": "unreadable" if error else "default", "error": error}
    return {"venues": {v: dict(row) for v, row in saved["venues"].items()}, "set_at": saved["set_at"],
            "source": "operator", "error": None}


def update(patch: Any, now: float | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply ``{paper?: {max_shares?, max_risk_usd?}, sim?: {...}}`` and save; ``(before, after)``.

    A null clears that limit. ``Invalid`` for a value out of its rule; ``OSError`` when the file cannot be
    written -- the setting is then unchanged. A save over a file this build could not use starts from every
    limit off and writes a fresh file. Blocking: call it off the event loop."""
    if not isinstance(patch, dict) or not patch:
        raise Invalid("Send {paper?: {max_shares?, max_risk_usd?}, sim?: {max_shares?, max_risk_usd?}}")
    unknown = sorted(set(patch) - set(ORDER_SIZE_LIMIT_VENUES))
    if unknown:
        raise Invalid(f"Unknown venue {', '.join(unknown)}: the order size limit is for Paper and Sim")
    with _save_lock:
        return _apply(patch, now)


def _apply(patch: dict[str, Any], now: float | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """``update``'s read, change and write, under ``_save_lock``."""
    global _loaded_from, _saved, _error
    before = current()
    after = {venue: dict(row) for venue, row in before["venues"].items()}
    for venue, row in patch.items():
        if not isinstance(row, dict) or not row:
            raise Invalid(f"Send {venue} as {{max_shares?, max_risk_usd?}}")
        extra = sorted(set(row) - set(ORDER_SIZE_LIMIT_FIELDS))
        if extra:
            raise Invalid(f"Unknown setting {', '.join(extra)}")
        for field, value in row.items():
            problem = _problem(field, value)
            if problem:
                raise Invalid(problem)
            after[venue][field] = None if value is None else int(value)
    from capture.manifest_io import write_json_atomic

    ts = time.time() if now is None else float(now)
    target = path()
    write_json_atomic(target, {"schema_version": ORDER_SIZE_LIMIT_SCHEMA_VERSION, "venues": after, "set_at": ts})
    with _lock:
        _loaded_from, _saved, _error = target, {"venues": after, "set_at": ts}, None
    logger.info("ORDER SIZE LIMIT: the operator set %s", after)
    return before, current()


def reset_for_tests() -> None:
    global _loaded_from, _saved, _error
    with _lock:
        _loaded_from, _saved, _error = None, None, None
