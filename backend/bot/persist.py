"""Bot persisted files.

Owner: this module (session + proposals + audit JSONL).
Invalidation: process start loads; L0 does not delete history; schema bump.
schema_version: BOT_SCHEMA_VERSION.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from bot.packs import default_pack_settings, merge_pack_settings
from constants_bot import (
    BOT_ACTION_KINDS,
    BOT_ADVISE_DEFAULT_CALL_CAP,
    BOT_ADVISE_DEFAULT_USD_CAP,
    BOT_AUDIT_FILENAME,
    BOT_DEFAULT_BP_BUDGET_USD,
    BOT_DEFAULT_MAX_SHARES,
    BOT_DEFAULT_WORKING_TTL_SEC,
    BOT_LEVEL_OFF,
    BOT_LLM_DEFAULT_CALL_CAP,
    BOT_LLM_DEFAULT_USD_CAP,
    BOT_PACK_DEFAULT,
    BOT_PROPOSALS_FILENAME,
    BOT_SCHEMA_VERSION,
    BOT_SCHEMA_VERSIONS,
    BOT_SESSION_FILENAME,
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
    return {
        "schema_version": BOT_SCHEMA_VERSION,
        "level": BOT_LEVEL_OFF,
        "armed": False,
        "strategy": None,
        "brain_session_id": None,
        "desk_arm_token": None,
        "claim_arm_token": None,
        "brain_heartbeat_ts": None,
        "active_pack": BOT_PACK_DEFAULT,
        "symbol_allowlist": [],
        "pack_settings": default_pack_settings(),
        "caps": {
            "max_shares": BOT_DEFAULT_MAX_SHARES,
            "bp_budget_usd": BOT_DEFAULT_BP_BUDGET_USD,
            "working_ttl_sec": BOT_DEFAULT_WORKING_TTL_SEC,
            "extended_hours": False,
            "allowlist": list(BOT_ACTION_KINDS),
        },
        "advise": {
            "enabled": False,
            "usd_cap": BOT_ADVISE_DEFAULT_USD_CAP,
            "call_cap": BOT_ADVISE_DEFAULT_CALL_CAP,
            "usd_spent": 0.0,
            "calls_used": 0,
        },
        "llm": {
            "call_cap": BOT_LLM_DEFAULT_CALL_CAP,
            "usd_cap": BOT_LLM_DEFAULT_USD_CAP,
            "usd_spent": 0.0,
            "calls_used": 0,
        },
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
        merged = default_session()
        merged.update(raw)
        merged["caps"] = {**default_session()["caps"], **(raw.get("caps") or {})}
        merged["advise"] = {**default_session()["advise"], **(raw.get("advise") or {})}
        merged["llm"] = {**default_session()["llm"], **(raw.get("llm") or {})}
        merged["pack_settings"] = merge_pack_settings(raw.get("pack_settings"))
        _session = merged
        return _session


def save_session(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global _session
    with _lock:
        data = dict(payload if payload is not None else load_session())
        data["schema_version"] = BOT_SCHEMA_VERSION
        data["updated_ts"] = time.time()
        _session = data
        path = _session_path()
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
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
        _proposals_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
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


def reset_for_tests() -> None:
    global _session, _proposals
    with _lock:
        _session = None
        _proposals = None
        try:
            for path in (_session_path(), _proposals_path(), _audit_path()):
                if path.exists():
                    path.unlink()
        except (OSError, NotImplementedError):
            logger.warning("bot persist: test reset skipped disk unlink")
