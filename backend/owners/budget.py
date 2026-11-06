"""The bots' budget on Paper: every bot together, at most this much in open positions (ADR 069 decision 5).

The file ``owners-budget.json`` in the operator cache: ``{schema_version: 1, bots_usd, set_at}``, whole
dollars. Owner: this module. Invalidation: rewritten whole on every change. No file reads the default
($25,000, the operator's 2026-11-03 choice); an unknown version or an unreadable file reads the default,
logged and stated in ``error`` -- never a silent guess -- and the next save writes a fresh file.

What counts against it (``used_usd``): the bots' open shares at the mark plus their working entries at their
own price (an order that opens or adds; a close never counts).
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from pathlib import Path
from typing import Any

from constants_owners import (
    OWNERS_BOTS_BUDGET_DEFAULT_USD,
    OWNERS_BOTS_BUDGET_MAX_USD,
    OWNERS_BOTS_BUDGET_MIN_USD,
    OWNERS_BUDGET_FILE,
    OWNERS_BUDGET_SCHEMA_VERSION,
    OWNER_BOTS,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_loaded_from: Path | None = None
_saved: dict[str, Any] | None = None
_error: str | None = None


class Invalid(ValueError):
    """A budget this setting refuses; the message says the rule."""


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / OWNERS_BUDGET_FILE


def _problem(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return "The bots' budget is a dollar amount"
    if value != int(value):
        return "The bots' budget is whole dollars"
    if not OWNERS_BOTS_BUDGET_MIN_USD <= value <= OWNERS_BOTS_BUDGET_MAX_USD:
        return f"The bots' budget is between ${OWNERS_BOTS_BUDGET_MIN_USD:,} and ${OWNERS_BOTS_BUDGET_MAX_USD:,}"
    return None


def read(at: Path) -> tuple[dict[str, Any] | None, str | None]:
    """``(saved, error)``: ``(None, None)`` with no file; ``(None, why)`` for one this build cannot use."""
    try:
        doc = json.loads(at.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        logger.warning("OWNERS: %s is unreadable -- the default budget applies", at, exc_info=True)
        return None, f"Nova could not read the saved bots' budget ({type(exc).__name__}), so the default applies"
    version = doc.get("schema_version") if isinstance(doc, dict) else None
    if version != OWNERS_BUDGET_SCHEMA_VERSION:
        logger.warning("OWNERS: %s has schema_version %s; this build reads %s -- the default budget applies",
                       at, version, OWNERS_BUDGET_SCHEMA_VERSION)
        return None, (f"The saved bots' budget is version {version}; this Nova reads version "
                      f"{OWNERS_BUDGET_SCHEMA_VERSION}, so the default applies")
    if _problem(doc.get("bots_usd")):
        logger.warning("OWNERS: %s holds a budget this build cannot use -- the default applies", at)
        return None, "The saved bots' budget holds a value Nova cannot use, so the default applies"
    set_at = doc.get("set_at")
    return {"bots_usd": int(doc["bots_usd"]),
            "set_at": float(set_at) if isinstance(set_at, (int, float)) else None}, None


def _ensure_loaded() -> None:
    global _loaded_from, _saved, _error
    target = path()
    if _loaded_from == target:
        return
    saved, error = read(target)
    with _lock:
        _loaded_from, _saved, _error = target, saved, error


def current() -> dict[str, Any]:
    """``{bots_usd, set_at, source: "default" | "operator", error}``."""
    _ensure_loaded()
    saved, error = _saved, _error
    if saved is None:
        return {"bots_usd": OWNERS_BOTS_BUDGET_DEFAULT_USD, "set_at": None, "source": "default", "error": error}
    return {**saved, "source": "operator", "error": None}


def bots_usd() -> int:
    return int(current()["bots_usd"])


def update(bots: Any, now: float | None = None) -> dict[str, Any]:
    """Save a new budget; ``Invalid`` for a value out of its rule, ``OSError`` when the file cannot be written.
    Blocking: call it off the event loop."""
    global _loaded_from, _saved, _error
    problem = _problem(bots)
    if problem:
        raise Invalid(problem)
    from capture.manifest_io import write_json_atomic

    ts = time.time() if now is None else float(now)
    target = path()
    write_json_atomic(target, {"schema_version": OWNERS_BUDGET_SCHEMA_VERSION, "bots_usd": int(bots), "set_at": ts})
    with _lock:
        _loaded_from, _saved, _error = target, {"bots_usd": int(bots), "set_at": ts}, None
    logger.info("OWNERS: the operator set the bots' budget to $%s", int(bots))
    return current()


def used_usd(ledger: Any, *, exclude_order_id: int | None = None) -> float:
    """What the bots hold now on ``ledger``: open shares at the mark plus working entries at their price --
    all but ``exclude_order_id``'s, the entry being repriced or filled."""
    from owners.whose import book_of, holder_of

    owners = getattr(ledger, "owners", None)
    if owners is None:
        return 0.0
    used = 0.0
    for symbol, lots in owners.lots.items():
        for holder, lot in lots.items():
            if book_of(holder) == OWNER_BOTS and abs(lot.qty) > 1e-9:
                used += abs(lot.qty) * float(ledger.mark_of(symbol, lot.avg) or lot.avg)
    for row in ledger.working_orders():
        if row.get("effect") != "opens" or book_of(holder_of(row)) != OWNER_BOTS:
            continue
        if exclude_order_id is not None and int(row.get("order_id") or -1) == int(exclude_order_id):
            continue
        price = row.get("limit_price") or row.get("stop_price") or ledger.mark_of(str(row["symbol"]))
        used += float(row.get("remaining_qty") or row.get("qty") or 0) * float(price or 0)
    return used


def reset_for_tests() -> None:
    global _loaded_from, _saved, _error
    with _lock:
        _loaded_from, _saved, _error = None, None, None
