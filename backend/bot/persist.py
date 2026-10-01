"""Bot persisted files.

Owner: this module (session + proposals + audit JSONL).
Invalidation: process start loads (and clears Activate: it never survives a start,
``bot.activation``); L0 does not delete history; schema bump.
schema_version: BOT_SCHEMA_VERSION. A v1-4 session migrates on load (ADR 042:
``bot.venue_levels.migrate_v5``); an unknown version refuses loudly.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from constants_bot import (
    BOT_AUDIT_FILENAME,
    BOT_BREAKER_VENUES,
    BOT_LEVEL_OFF,
    BOT_LEVEL_UNRESTRICTED,
    BOT_PROPOSALS_FILENAME,
    BOT_RETIRED_SESSION_KEYS,
    BOT_RETIRED_V5_KEYS,
    BOT_SCHEMA_VERSION,
    BOT_SCHEMA_VERSIONS,
    BOT_SESSION_FILENAME,
    BOT_SETUP_DEFAULT,
)
from paths import cache_dir

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_session: dict[str, Any] | None = None
_proposals: dict[str, Any] | None = None


def _session_path() -> Path:
    return cache_dir() / BOT_SESSION_FILENAME


def _proposals_path() -> Path:
    return cache_dir() / BOT_PROPOSALS_FILENAME


def _audit_path() -> Path:
    return cache_dir() / BOT_AUDIT_FILENAME


def default_session() -> dict[str, Any]:
    from bot.sleeve import defaults as sleeve_defaults

    return {
        "schema_version": BOT_SCHEMA_VERSION,
        "level": BOT_LEVEL_OFF,
        "armed": False,
        "brain_session_id": None,
        "desk_arm_token": None,
        "claim_arm_token": None,
        "brain_heartbeat_ts": None,
        "setup_levels": {},
        "symbol_allowlist": [],
        "caps": sleeve_defaults(),
        "deactivated": None,
        "soft_breaker_fired": False,
        "hard_lock_until_date": None,
        "bot_qty": {},
        "working": [],
        "focus": [],
        "trader_live": [],
        "updated_ts": time.time(),
    }


def default_proposals() -> dict[str, Any]:
    return {"schema_version": BOT_SCHEMA_VERSION, "items": []}


def _refuse_unknown(raw: Any, label: str) -> None:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} is not an object")
    version = raw.get("schema_version")
    if version is None:
        raw["schema_version"] = BOT_SCHEMA_VERSION
        return
    if int(version) not in BOT_SCHEMA_VERSIONS:
        raise ValueError(
            f"{label} schema_version={version!r} (expected one of {BOT_SCHEMA_VERSIONS})"
        )


def _refuse_parked_level(row: dict[str, Any]) -> None:
    """Load dark on any level at or above the parked one (#216).

    `apply_patch` refuses to *write* L3, but that guard only covers the write
    door. A session file that carries a parked or unknown level -- stale state
    from another build, a hand-edited file -- must not come back live.
    """
    try:
        level = int(row.get("level") or BOT_LEVEL_OFF)
    except (TypeError, ValueError):
        level = BOT_LEVEL_UNRESTRICTED
    if level < BOT_LEVEL_UNRESTRICTED:
        return
    logger.warning(
        "bot persist: session file carries parked autonomy level %s -- loading dark", level
    )
    row["level"] = BOT_LEVEL_OFF
    row["armed"] = False


def _write_atomic(path: Path, text: str) -> None:
    """Write through a temp file and a rename, so a crash mid-save never leaves half a file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def load_session() -> dict[str, Any]:
    global _session
    with _lock:
        if _session is not None:
            return _session
        path = _session_path()
        if not path.exists():
            _session = default_session()
            return _session
        raw = json.loads(path.read_text(encoding="utf-8"))
        _refuse_unknown(raw, BOT_SESSION_FILENAME)
        version = int(raw.get("schema_version") or BOT_SCHEMA_VERSION)
        merged = default_session()
        merged.update(raw)
        for key in BOT_RETIRED_SESSION_KEYS:  # ADR 027: the packs are gone (schema 4)
            merged.pop(key, None)
        if version < 5:
            _migrate_v5(merged)
        for key in BOT_RETIRED_V5_KEYS:       # ADR 042: no chosen setup, strategy or advise budget
            merged.pop(key, None)
        merged["schema_version"] = BOT_SCHEMA_VERSION
        _refuse_parked_level(merged)
        _session = merged
        # Activate never survives a process start (ADR 018 / 042), in memory at once.
        from bot.activation import clear_on_load

        clear_on_load(merged)
        _follow_desk_venue(merged)
        return _session


def _migrate_v5(row: dict[str, Any]) -> None:
    """Schema 4 -> 5 (ADR 042): the chosen setup's level, the sleeve, the bot list and the day
    lock move into each venue's dial (``bot.venue_levels.migrate_v5``)."""
    from bot.venue_levels import migrate_v5

    here = row.get("level_venue")
    if here not in BOT_BREAKER_VENUES:
        try:
            from sim.mode import venue

            here = venue()
        except Exception:
            logger.warning("bot persist: the desk venue is unreadable -- the v5 migration files the "
                           "session's own dial under Live (its bot list starts empty)", exc_info=True)
            here = "live"
    chosen = str(row.get("setup") or BOT_SETUP_DEFAULT)
    migrate_v5(row, str(here), chosen)
    logger.info("bot persist: session migrated to schema 5 (chosen setup %s, dial %s)", chosen, here)


def _follow_desk_venue(row: dict[str, Any]) -> None:
    """A session file whose level belongs to another venue than the desk's (the venue
    file changed while Nova was stopped) takes the desk venue's own level, not active."""
    try:
        from bot.venue_levels import switch
        from sim.mode import venue

        if switch(row, venue()) is not None:
            save_session(row)
    except Exception:
        logger.warning("bot persist: could not match the level to the desk venue", exc_info=True)


def save_session(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global _session
    with _lock:
        data = dict(payload if payload is not None else load_session())
        data["schema_version"] = BOT_SCHEMA_VERSION
        data["updated_ts"] = time.time()
        _session = data
        _write_atomic(_session_path(), json.dumps(data, indent=2))
        return data


def load_proposals() -> dict[str, Any]:
    global _proposals
    with _lock:
        if _proposals is not None:
            return _proposals
        path = _proposals_path()
        if not path.exists():
            _proposals = default_proposals()
            return _proposals
        raw = json.loads(path.read_text(encoding="utf-8"))
        _refuse_unknown(raw, BOT_PROPOSALS_FILENAME)
        _proposals = {
            "schema_version": BOT_SCHEMA_VERSION,
            "items": list(raw.get("items") or []),
        }
        return _proposals


def save_proposals(payload: dict[str, Any]) -> dict[str, Any]:
    global _proposals
    with _lock:
        data = {
            "schema_version": BOT_SCHEMA_VERSION,
            "items": list(payload.get("items") or []),
        }
        _proposals = data
        _write_atomic(_proposals_path(), json.dumps(data, indent=2))
        return data


def append_audit_line(row: dict[str, Any]) -> None:
    line = json.dumps(row, default=str)
    with _lock:
        with _audit_path().open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def read_audit_lines(*, limit: int = 200) -> list[dict[str, Any]]:
    path = _audit_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except ValueError:
                logger.warning("bot audit: skipped corrupt line")
    return rows[-max(1, int(limit)):]


def read_audit_tail(max_bytes: int) -> tuple[list[dict[str, Any]], bool]:
    """The audit lines in the file's last ``max_bytes`` (oldest first), and whether that is the whole file.

    A line cut by the window's start is dropped, never half-parsed; a corrupt line is skipped
    with a warning, like ``read_audit_lines``."""
    path = _audit_path()
    if not path.exists():
        return [], True
    with _lock, path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        start = max(0, size - max(1, int(max_bytes)))
        handle.seek(start)
        data = handle.read()
    lines = data.decode("utf-8", errors="replace").splitlines()
    if start > 0 and lines:
        lines = lines[1:]
    rows: list[dict[str, Any]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            rows.append(json.loads(text))
        except ValueError:
            logger.warning("bot audit: skipped corrupt line")
    return rows, start == 0


def audit_signature() -> tuple[int, int] | None:
    """``(mtime_ns, size)`` of the audit file, for a reader that caches what it folded; None when absent."""
    try:
        st = _audit_path().stat()
    except FileNotFoundError:
        return None
    return int(st.st_mtime_ns), int(st.st_size)


def reset_for_tests() -> None:
    global _session, _proposals
    from bot.activation import reset_for_tests as reset_activation

    reset_activation()
    with _lock:
        _session = None
        _proposals = None
        try:
            for path in (_session_path(), _proposals_path(), _audit_path()):
                if path.exists():
                    path.unlink()
        except (OSError, NotImplementedError):
            logger.warning("bot persist: test reset skipped disk unlink")
