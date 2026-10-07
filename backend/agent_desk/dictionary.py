"""The operator's dictionary of commands (ADR 050): their words, what they mean, the exact call.

Operator: "If I'm obviously asking for a command, such as this one, I want it to be added to our dictionary."
Every agent reads it before acting and adds the phrasing the operator confirms, so Claude, Codex and Cursor read
the operator the same way. ``<cache_dir>/agent-dictionary.json`` = ``{schema_version: 1, entries: [...]}``,
written through a temp file and a rename. The seeds live in code (``dictionary_seed``); an operator entry with
a seed's id replaces it. An unknown version or an unreadable file reads as the seeds with the error stated, and
writes are refused (``DictionaryUnreadable``) so nothing the operator saved is overwritten.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from agent_desk.dictionary_seed import SEED_ENTRIES
from constants_agent_desk import (
    AGENT_DICTIONARY_FILENAME,
    AGENT_DICTIONARY_ID_MAX,
    AGENT_DICTIONARY_MAX_ENTRIES,
    AGENT_DICTIONARY_SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_METHODS = ("GET", "POST", "DELETE")
_TEXT_MAX = 1000
_PHRASE_MAX = 200
_PHRASES_MAX = 20


class DictionaryUnreadable(RuntimeError):
    """The file exists but cannot be read as this version: writes would lose what it holds."""


class EntryInvalid(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def path() -> Path:
    from paths import cache_dir

    return Path(cache_dir()) / AGENT_DICTIONARY_FILENAME


def _read(target: Path) -> tuple[list[dict[str, Any]], str | None]:
    """The operator's entries and the error, if the file cannot be read as this version."""
    if not target.is_file():
        return [], None
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("agent dictionary %s unreadable: %s", target, exc)
        return [], f"{target.name} cannot be read ({type(exc).__name__}: {exc})"
    if not isinstance(raw, dict) or raw.get("schema_version") != AGENT_DICTIONARY_SCHEMA_VERSION:
        version = raw.get("schema_version") if isinstance(raw, dict) else None
        return [], f"{target.name} is schema_version {version!r}, not {AGENT_DICTIONARY_SCHEMA_VERSION}"
    entries = raw.get("entries")
    if not isinstance(entries, list):
        return [], f"{target.name} has no entries list"
    return [e for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)], None


def view(target: Path | None = None) -> dict[str, Any]:
    """``{schema_version, error, entries}``: the seeds, each replaced by the operator's entry of the same id."""
    own, error = _read(target or path())
    by_id = {e["id"]: dict(e, seed=True) for e in SEED_ENTRIES}
    for entry in own:
        by_id[entry["id"]] = dict(entry, seed=False)
    return {"schema_version": AGENT_DICTIONARY_SCHEMA_VERSION, "error": error, "entries": list(by_id.values())}


def _text(entry: dict[str, Any], field: str, *, required: bool = False, limit: int = _TEXT_MAX) -> str | None:
    value = entry.get(field)
    if value is None or value == "":
        if required:
            raise EntryInvalid(field, f"{field} is required")
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise EntryInvalid(field, f"{field} must be text of at most {limit} characters")
    return value.strip()


def clean(entry: Any) -> dict[str, Any]:
    """The entry as stored, or ``EntryInvalid`` naming the field."""
    if not isinstance(entry, dict):
        raise EntryInvalid("entry", "entry must be an object")
    entry_id = _text(entry, "id", required=True, limit=AGENT_DICTIONARY_ID_MAX)
    if not _ID.match(entry_id or ""):
        raise EntryInvalid("id", "id is lower-case letters, digits and dashes")
    phrases = entry.get("phrases")
    if (not isinstance(phrases, list) or not 1 <= len(phrases) <= _PHRASES_MAX
            or not all(isinstance(p, str) and 0 < len(p.strip()) <= _PHRASE_MAX for p in phrases)):
        raise EntryInvalid("phrases", f"phrases is a list of 1-{_PHRASES_MAX} phrases of at most {_PHRASE_MAX} characters")
    call = entry.get("call")
    if not isinstance(call, dict) or call.get("method") not in _METHODS:
        raise EntryInvalid("call", f"call needs a method ({', '.join(_METHODS)}) and a path under /api/agent")
    call_path = call.get("path")
    if not isinstance(call_path, str) or not call_path.startswith("/api/agent"):
        raise EntryInvalid("call.path", "call.path must be an /api/agent route")
    for part in ("params", "body"):
        if call.get(part) is not None and not isinstance(call[part], dict):
            raise EntryInvalid(f"call.{part}", f"call.{part} must be an object")
    out = {
        "id": entry_id,
        "phrases": [p.strip() for p in phrases],
        "means": _text(entry, "means", required=True),
        "call": {k: call[k] for k in ("method", "path", "params", "body") if call.get(k) is not None},
        "then": _text(entry, "then"),
        "notes": _text(entry, "notes"),
        "added_by": _text(entry, "added_by", limit=64) or "agent",
    }
    return {k: v for k, v in out.items() if v is not None}


def _write(target: Path, entries: list[dict[str, Any]]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + f".tmp{os.getpid()}")
    payload = {"schema_version": AGENT_DICTIONARY_SCHEMA_VERSION, "entries": entries}
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def put(entry: Any, *, target: Path | None = None, now: float | None = None) -> dict[str, Any]:
    """Add or replace the operator's entry by id; the stored entry."""
    target = target or path()
    stored = clean(entry)
    own, error = _read(target)
    if error is not None:
        raise DictionaryUnreadable(error)
    at = time.time() if now is None else now
    previous = next((e for e in own if e["id"] == stored["id"]), None)
    stored["added_at"] = previous.get("added_at", at) if previous else at
    stored["updated_at"] = at
    entries = [e for e in own if e["id"] != stored["id"]] + [stored]
    if len(entries) > AGENT_DICTIONARY_MAX_ENTRIES:
        raise EntryInvalid("entry", f"the dictionary holds at most {AGENT_DICTIONARY_MAX_ENTRIES} entries")
    _write(target, entries)
    return dict(stored, seed=False)


def remove(entry_id: str, *, target: Path | None = None) -> bool:
    """Drop the operator's entry; a seed cannot be removed (its id comes back as the seed)."""
    target = target or path()
    own, error = _read(target)
    if error is not None:
        raise DictionaryUnreadable(error)
    kept = [e for e in own if e["id"] != entry_id]
    if len(kept) == len(own):
        return False
    _write(target, kept)
    return True
