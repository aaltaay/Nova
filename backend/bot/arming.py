"""Desk Activate token + brain heartbeat (ADR 016 arming lock).

Owner: this module (token issue/disarm + heartbeat stamp).
Invalidation: Stop, L0, new Activate, or a stale heartbeat window.
schema_version: BOT_SCHEMA_VERSION on the session file.
"""
from __future__ import annotations

import hmac
import secrets
import time
from typing import Any

from bot.errors import BotError
from bot.persist import load_session, save_session
from constants_bot import (
    BOT_HEARTBEAT_STALE_SEC,
    BOT_REASON_ARM_DESK_ONLY,
    BOT_REASON_ARM_REQUIRED,
    BOT_REASON_BRAIN_EXCLUSIVE,
    BOT_REASON_HEARTBEAT_STALE,
)


def issue_arm_token(*, reenable: bool = False) -> str:
    """Desk Activate. Rotates the token and drops any prior brain claim."""
    row = load_session()
    token = secrets.token_urlsafe(24)
    row["desk_arm_token"] = token
    row["armed"] = True
    row["brain_session_id"] = None
    row["claim_arm_token"] = None
    row["brain_heartbeat_ts"] = None
    if reenable:
        row["soft_breaker_fired"] = False
    save_session(row)
    return token


def disarm_session() -> dict[str, Any]:
    """Desk Stop. Claim cannot outlive Activate."""
    row = load_session()
    _clear_arm_state(row)
    return save_session(row)


def clear_arm_fields(row: dict[str, Any]) -> dict[str, Any]:
    _clear_arm_state(row)
    return row


def require_matching_arm_token(row: dict[str, Any], arm_token: str | None) -> str:
    held = (row.get("desk_arm_token") or "").strip()
    incoming = (arm_token or "").strip()
    if not held or not incoming or not hmac.compare_digest(incoming, held):
        raise BotError(
            "raising autonomy above L1 needs a desk arm token from header Activate",
            403,
            BOT_REASON_ARM_REQUIRED,
        )
    return incoming


def assert_desk_activate(brain_session_id: str | None) -> None:
    if (brain_session_id or "").strip():
        raise BotError(
            "brains cannot Activate or Stop -- desk header only",
            403,
            BOT_REASON_ARM_DESK_ONLY,
        )


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


def _clear_arm_state(row: dict[str, Any]) -> None:
    row["desk_arm_token"] = None
    row["armed"] = False
    row["brain_session_id"] = None
    row["claim_arm_token"] = None
    row["brain_heartbeat_ts"] = None
