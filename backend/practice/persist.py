"""On-disk form of the Paper ledger (persisted-state.mdc).

Owner: ``practice/ledger.py`` through this module -- nothing else reads or
writes ``practice-paper.json`` under the operator cache. Invalidation: an
operator reset, which archives the file as
``practice-paper-<YYYYMMDD-HHMMSS>.json`` beside it (never deleted), or a file
this build cannot read -- an unknown ``schema_version`` or malformed body is
refused loud (``LedgerSchemaError``) and the broker archives it the same way
before starting fresh, so no practice history is ever overwritten silently.
Writes are atomic: a temp file in the same directory, then ``os.replace``.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from typing import Any

from constants_practice import (
    PRACTICE_LEDGER_SCHEMA_VERSION,
    PRACTICE_PAPER_ARCHIVE_STAMP,
    PRACTICE_PAPER_LEDGER_FILE,
)
from practice.ledger import ET, EVENT_TYPES, Ledger

logger = logging.getLogger(__name__)


class LedgerSchemaError(ValueError):
    """Not a practice ledger this build can read. Refused, never guessed at."""


def paper_ledger_path() -> str:
    from paths import cache_dir

    return os.path.join(str(cache_dir()), PRACTICE_PAPER_LEDGER_FILE)


def to_dict(ledger: Ledger) -> dict[str, Any]:
    return {
        "schema_version": PRACTICE_LEDGER_SCHEMA_VERSION,
        "starting_cash": ledger.starting_cash,
        "created_ts": ledger.created_ts,
        "events": [dict(e) for e in ledger.events],
    }


def from_dict(data: Any) -> Ledger:
    if not isinstance(data, dict):
        raise LedgerSchemaError("practice ledger is not a JSON object")
    try:
        version = int(data.get("schema_version"))
    except (TypeError, ValueError) as exc:
        raise LedgerSchemaError(
            f"practice ledger schema_version {data.get('schema_version')!r} is not a number"
        ) from exc
    if version != PRACTICE_LEDGER_SCHEMA_VERSION:
        raise LedgerSchemaError(
            f"practice ledger schema_version {version} is unknown "
            f"(this build reads {PRACTICE_LEDGER_SCHEMA_VERSION})"
        )
    events = data.get("events")
    if not isinstance(events, list) or any(
        not isinstance(e, dict) or e.get("type") not in EVENT_TYPES or "ts" not in e
        for e in events
    ):
        raise LedgerSchemaError("practice ledger events are malformed")
    try:
        return Ledger(
            float(data.get("starting_cash")),
            created_ts=float(data.get("created_ts")),
            events=events,
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise LedgerSchemaError(f"practice ledger body is malformed: {exc}") from exc


def save(ledger: Ledger, path: str) -> None:
    """Atomic write: temp file beside ``path``, then ``os.replace``."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".practice-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(to_dict(ledger), f)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            logger.debug("PRACTICE persist: temp cleanup failed for %s", tmp, exc_info=True)
        raise


def load(path: str) -> Ledger | None:
    """The ledger at ``path``; ``None`` when there is no file; refuses what it cannot read."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise LedgerSchemaError(f"practice ledger {path} is unreadable: {exc}") from exc
    return from_dict(data)


def archive_path(path: str, now: datetime | None = None, attempt: int = 0) -> str:
    stamp = (now or datetime.now(ET)).strftime(PRACTICE_PAPER_ARCHIVE_STAMP)
    root, ext = os.path.splitext(path)
    suffix = f"-{attempt}" if attempt else ""
    return f"{root}-{stamp}{suffix}{ext}"


def list_archives(path: str) -> list[str]:
    """Every archived sibling of ``path`` (``<root>-<stamp>[-n]<ext>``), oldest stamp first.

    Never the live file and never a ``.practice-*.tmp`` write in flight. Raises
    ``OSError`` when the directory cannot be listed; the caller says so.
    """
    directory = os.path.dirname(os.path.abspath(path))
    root, ext = os.path.splitext(os.path.basename(path))
    prefix = f"{root}-"
    names = [n for n in os.listdir(directory) if n.startswith(prefix) and n.endswith(ext)]
    return [os.path.join(directory, n) for n in sorted(names)]


def archive(path: str, *, now: datetime | None = None) -> str | None:
    """Rename ``path`` to its stamped sibling; ``None`` when there is nothing to archive."""
    if not os.path.exists(path):
        return None
    for attempt in range(100):
        target = archive_path(path, now, attempt)
        if os.path.exists(target):
            continue
        os.rename(path, target)
        logger.info("PRACTICE persist: archived %s as %s", path, target)
        return target
    raise OSError(f"could not find a free archive name for {path}")
