"""The Live short proof's file: ``short-proof.json`` in the operator cache (ADR 048 step 6).

Shape (schema 1)::

    {schema_version: 1,
     days: {"YYYY-MM-DD": {orders: [order id], symbols: [SYMBOL], first_ts, last_ts}},
     drills: {freeze | flatten | day_cover | gateway_drop: {passed: Run | null, failed: [Run]}},
     reviews: {"YYYY-MM-DD": object}}

A day is a Paper practice day (from 04:00 ET) with filled short entries, by order id. A Run is ``{at,
symbol, qty, detail}`` plus the drill's own facts; a drill keeps its first passing run and its last
``SHORT_PROOF_FAILED_KEEP`` that did not pass. ``reviews`` is empty until the operator's answer on #778
(question 3) says how a day is reviewed.

Only the observer and the kill switch's hook write it, through a temp file and a rename. It is read
once into memory and kept there (the door reads the proof under its lock: never the disk). An
unknown version or a file Nova cannot read is an error: nothing is recorded or written over it, and
the proof reads incomplete with the reason.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from constants_shorts import (
    SHORT_PROOF_DRILLS,
    SHORT_PROOF_FAILED_KEEP,
    SHORT_PROOF_FILE,
    SHORT_PROOF_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

_lock = threading.RLock()
# (path it was read from, document or None, error or None)
_loaded: tuple[str, dict[str, Any] | None, str | None] | None = None


def path() -> Path:
    from paths import cache_root

    return cache_root() / SHORT_PROOF_FILE


def empty() -> dict[str, Any]:
    return {"schema_version": SHORT_PROOF_SCHEMA_VERSION, "days": {},
            "drills": {name: {"passed": None, "failed": []} for name in SHORT_PROOF_DRILLS}, "reviews": {}}


def _shape(raw: Any) -> dict[str, Any]:
    """A read document in the current shape; anything missing reads as nothing recorded yet."""
    doc = empty()
    days = raw.get("days") if isinstance(raw.get("days"), dict) else {}
    for day, entry in days.items():
        if isinstance(day, str) and isinstance(entry, dict):
            doc["days"][day] = {"orders": [int(o) for o in entry.get("orders") or [] if isinstance(o, int)],
                                "symbols": [str(s) for s in entry.get("symbols") or []],
                                "first_ts": entry.get("first_ts"), "last_ts": entry.get("last_ts")}
    drills = raw.get("drills") if isinstance(raw.get("drills"), dict) else {}
    for name in SHORT_PROOF_DRILLS:
        got = drills.get(name) if isinstance(drills.get(name), dict) else {}
        passed = got.get("passed") if isinstance(got.get("passed"), dict) else None
        failed = [r for r in got.get("failed") or [] if isinstance(r, dict)][-SHORT_PROOF_FAILED_KEEP:]
        doc["drills"][name] = {"passed": passed, "failed": failed}
    if isinstance(raw.get("reviews"), dict):
        doc["reviews"] = raw["reviews"]
    return doc


def _parse(p: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not p.exists():
        return empty(), None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except OSError:
        logger.exception("short proof: %s could not be read -- the proof reads incomplete", p)
        return None, f"{p.name} could not be read from disk; the engine log has the details"
    except ValueError:
        logger.exception("short proof: %s is not valid JSON -- the proof reads incomplete", p)
        return None, f"{p.name} is not valid JSON; the engine log has the details"
    if not isinstance(raw, dict) or raw.get("schema_version") != SHORT_PROOF_SCHEMA_VERSION:
        version = raw.get("schema_version") if isinstance(raw, dict) else None
        logger.error("short proof: %s has schema_version %r, not %s -- refused", p, version, SHORT_PROOF_SCHEMA_VERSION)
        return None, f"{p.name} has an unknown schema_version ({version!r}); Nova reads only version 1"
    return _shape(raw), None


def _current() -> tuple[dict[str, Any] | None, str | None]:
    """The document in memory, read from disk once per path (tests move the cache)."""
    global _loaded
    p = str(path())
    with _lock:
        if _loaded is None or _loaded[0] != p:
            doc, error = _parse(Path(p))
            _loaded = (p, doc, error)
        return _loaded[1], _loaded[2]


def read() -> tuple[dict[str, Any] | None, str | None]:
    """A copy of the proof, and why it could not be read (then the copy is None)."""
    doc, error = _current()
    return (copy.deepcopy(doc) if doc is not None else None), error


def _write(doc: dict[str, Any]) -> None:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name, dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:  # maintainer: allow-swallow the temp file may already be gone
            pass
        raise


def _change(apply: Any) -> bool:
    """Apply ``apply(doc) -> bool`` (True: changed) to the proof and write it; False when nothing changed.

    A proof Nova cannot read is never written over (its error stands, and is logged once a change is lost).
    """
    with _lock:
        doc, error = _current()
        if doc is None:
            logger.error("short proof: a change was not recorded -- %s", error)
            return False
        work = copy.deepcopy(doc)
        if not apply(work):
            return False
        try:
            _write(work)
        except OSError:
            logger.exception("short proof: %s could not be written -- the change stays in memory only", path())
        global _loaded
        _loaded = (str(path()), work, None)
        return True


def record_short_fills(fills: list[dict[str, Any]]) -> bool:
    """Filled short entries on Paper, ``[{day, order_id, symbol, ts}]``; True when any was new."""
    def apply(doc: dict[str, Any]) -> bool:
        changed = False
        for fill in fills:
            day, order_id, symbol, ts = fill["day"], int(fill["order_id"]), str(fill["symbol"]), float(fill["ts"])
            entry = doc["days"].setdefault(day, {"orders": [], "symbols": [], "first_ts": ts, "last_ts": ts})
            if order_id in entry["orders"]:
                continue
            entry["orders"].append(order_id)
            if symbol not in entry["symbols"]:
                entry["symbols"].append(symbol)
            entry["first_ts"] = min(float(entry.get("first_ts") or ts), ts)
            entry["last_ts"] = max(float(entry.get("last_ts") or ts), ts)
            changed = True
        return changed

    return bool(fills) and _change(apply)


def record_drill(name: str, passed: bool, run: dict[str, Any]) -> bool:
    """One run of drill ``name``; a passing one is kept only when the drill has not passed yet."""
    if name not in SHORT_PROOF_DRILLS:
        raise ValueError(f"unknown drill {name!r}")

    def apply(doc: dict[str, Any]) -> bool:
        drill = doc["drills"][name]
        if passed:
            if drill["passed"] is not None:
                return False
            drill["passed"] = dict(run)
            return True
        if any(r.get("key") == run.get("key") for r in drill["failed"]):
            return False
        drill["failed"] = (drill["failed"] + [dict(run)])[-SHORT_PROOF_FAILED_KEEP:]
        return True

    return _change(apply)


def reset_for_tests() -> None:
    global _loaded
    with _lock:
        _loaded = None
