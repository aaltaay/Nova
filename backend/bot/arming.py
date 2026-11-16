"""The bot session's Activate fields and the brain's heartbeat (ADR 016 arming lock).

ADR 072: the Bot switch and Activate are retired, so nothing turns Activate on any more. The fields stay in the
session file: a file from before the upgrade is read with them cleared (``bot.persist``: Activate never survives a
start), and the bot API's door reads them shut (``bot.door``) until the brain's own switch replaces them.

Owner: this module (the Activate fields' rules and the heartbeat stamp; the file is ``bot.persist``'s).
Invalidation: a process start, a venue change, or a stale heartbeat window.
schema_version: BOT_SCHEMA_VERSION on the session file.
"""
from __future__ import annotations

import time
from typing import Any

from bot.errors import BotError
from bot.persist import load_session, save_session
from constants_bot import (
    BOT_HEARTBEAT_STALE_SEC,
    BOT_REASON_BRAIN_EXCLUSIVE,
    BOT_REASON_HEARTBEAT_STALE,
)


def clear_arm_fields(row: dict[str, Any]) -> bool:
    """Clear Activate and the brain's claim on ``row`` (the caller saves it). Returns whether Activate was on."""
    was = is_desk_active(row)
    row["desk_arm_token"] = None
    row["armed"] = False
    row["brain_session_id"] = None
    row["claim_arm_token"] = None
    row["brain_heartbeat_ts"] = None
    return was


def is_desk_active(row: dict[str, Any]) -> bool:
    """Session SSOT: Activate is on (``armed`` and a desk token)."""
    return bool(row.get("armed")) and bool((row.get("desk_arm_token") or "").strip())


def heartbeat_is_fresh(row: dict[str, Any], *, now: float | None = None) -> bool:
    ts = row.get("brain_heartbeat_ts")
    if not isinstance(ts, (int, float)):
        return False
    return (now if now is not None else time.time()) - float(ts) <= BOT_HEARTBEAT_STALE_SEC


def record_heartbeat(brain_session_id: str | None) -> dict[str, Any]:
    from bot.session import require_l2_brain

    require_l2_brain(brain_session_id, claim=False)
    row = load_session()
    incoming = (brain_session_id or "").strip()
    held = (row.get("brain_session_id") or "").strip()
    if not incoming or incoming != held:
        raise BotError(
            "heartbeat must come from the exclusive claimed brain",
            409,
            BOT_REASON_BRAIN_EXCLUSIVE,
        )
    row["brain_heartbeat_ts"] = time.time()
    return save_session(row)


def assert_fresh_heartbeat(row: dict[str, Any]) -> None:
    if not heartbeat_is_fresh(row):
        raise BotError(
            "brain heartbeat is missing or stale -- live fire is fail-closed",
            409,
            BOT_REASON_HEARTBEAT_STALE,
        )
