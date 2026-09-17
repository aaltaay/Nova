"""Bot session snapshot + exclusive L2 brain claim."""
from __future__ import annotations

from typing import Any

from bot import persist
from bot.arming import heartbeat_is_fresh
from bot.clock import lock_is_active
from bot.eligibility import normalize_symbols
from bot.errors import BotError
from bot.kinds import default_allowlist
from bot.llm_guard import public_llm
from bot.packs import catalog, default_pack_settings, normalize_pack
from constants_bot import (
    BOT_ADVISE_DEFAULT_CALL_CAP,
    BOT_ADVISE_DEFAULT_USD_CAP,
    BOT_BP_BUDGET_HARD_MAX_USD,
    BOT_LEVEL_OFF,
    BOT_LEVEL_STRATEGY,
    BOT_MAX_SHARES_CAP,
    BOT_REASON_ARM_REQUIRED,
    BOT_REASON_BRAIN_EXCLUSIVE,
    BOT_WORKING_TTL_MAX_SEC,
    BOT_WORKING_TTL_MIN_SEC,
)


def get_session() -> dict[str, Any]:
    row = persist.load_session()
    return public_view(row)


def public_view(row: dict[str, Any]) -> dict[str, Any]:
    level = int(row.get("level") or BOT_LEVEL_OFF)
    advise = dict(row.get("advise") or {})
    caps = dict(row.get("caps") or {})
    lock_until = row.get("hard_lock_until_date")
    token_on = bool((row.get("desk_arm_token") or "").strip())
    armed = bool(row.get("armed")) and token_on
    brain_id = row.get("brain_session_id") if level >= BOT_LEVEL_STRATEGY else None
    alive = heartbeat_is_fresh(row) and bool(brain_id)
    return {
        "level": level,
        "armed": armed,
        "has_desk_arm": token_on,
        "strategy": row.get("strategy") if level >= BOT_LEVEL_STRATEGY else None,
        "active_pack": normalize_pack(row.get("active_pack")),
        "packs": catalog(),
        "symbol_allowlist": normalize_symbols(row.get("symbol_allowlist")),
        "pack_settings": {**default_pack_settings(), **dict(row.get("pack_settings") or {})},
        "brain_session_id": brain_id,
        "brain_heartbeat_ts": row.get("brain_heartbeat_ts") if brain_id else None,
        "brain_alive": alive,
        "live_fire_ready": (
            level >= BOT_LEVEL_STRATEGY and armed and alive and bool(brain_id)
        ),
        "caps": {
            "max_shares": int(caps.get("max_shares") or 1),
            "bp_budget_usd": float(caps.get("bp_budget_usd") or 0),
            "working_ttl_sec": int(caps.get("working_ttl_sec") or 3),
            "extended_hours": bool(caps.get("extended_hours")),
            "allowlist": list(caps.get("allowlist") or default_allowlist()),
        },
        "advise": {
            "enabled": bool(advise.get("enabled")) and level > BOT_LEVEL_OFF,
            "usd_cap": float(advise.get("usd_cap") or BOT_ADVISE_DEFAULT_USD_CAP),
            "call_cap": int(advise.get("call_cap") or BOT_ADVISE_DEFAULT_CALL_CAP),
            "usd_spent": float(advise.get("usd_spent") or 0),
            "calls_used": int(advise.get("calls_used") or 0),
        },
        "llm": public_llm(row),
        "soft_breaker_fired": bool(row.get("soft_breaker_fired")),
        "hard_lock_until_date": lock_until,
        "day_lock_active": lock_is_active(lock_until),
        "focus": list(row.get("focus") or []),
        "trader_live": list(row.get("trader_live") or []),
        "working": list(row.get("working") or []),
        "updated_ts": row.get("updated_ts"),
    }


def raw() -> dict[str, Any]:
    return persist.load_session()


def save(row: dict[str, Any]) -> dict[str, Any]:
    return persist.save_session(row)


def clamp_caps(caps: dict[str, Any]) -> dict[str, Any]:
    out = dict(caps)
    shares = int(out.get("max_shares") or 1)
    out["max_shares"] = max(1, min(BOT_MAX_SHARES_CAP, shares))
    budget = float(out.get("bp_budget_usd") or 0)
    out["bp_budget_usd"] = max(0.01, min(BOT_BP_BUDGET_HARD_MAX_USD, budget))
    ttl = int(out.get("working_ttl_sec") or 3)
    out["working_ttl_sec"] = max(BOT_WORKING_TTL_MIN_SEC, min(BOT_WORKING_TTL_MAX_SEC, ttl))
    out["extended_hours"] = bool(out.get("extended_hours"))
    allow = [k for k in (out.get("allowlist") or default_allowlist()) if k in default_allowlist()]
    out["allowlist"] = allow or default_allowlist()
    return out


def require_l2_brain(brain_session_id: str | None, *, claim: bool = True) -> str:
    row = persist.load_session()
    if int(row.get("level") or 0) != BOT_LEVEL_STRATEGY:
        raise BotError("L2 brain required only at Strategy level", 409, BOT_REASON_BRAIN_EXCLUSIVE)
    desk_token = (row.get("desk_arm_token") or "").strip()
    if not row.get("armed") or not desk_token:
        raise BotError(
            "Activate from the desk header before a brain can claim",
            409,
            BOT_REASON_ARM_REQUIRED,
        )
    incoming = (brain_session_id or "").strip()
    if not incoming:
        raise BotError(
            "brain_session_id is required for the exclusive L2 session",
            409,
            BOT_REASON_BRAIN_EXCLUSIVE,
        )
    held = (row.get("brain_session_id") or "").strip()
    claim_token = (row.get("claim_arm_token") or "").strip()
    if held and claim_token != desk_token:
        row["brain_session_id"] = None
        row["claim_arm_token"] = None
        row["brain_heartbeat_ts"] = None
        held = ""
    if not held:
        if not claim:
            raise BotError(
                "brain_session_id is required for the exclusive L2 session",
                409,
                BOT_REASON_BRAIN_EXCLUSIVE,
            )
        row["brain_session_id"] = incoming
        row["claim_arm_token"] = desk_token
        persist.save_session(row)
        return incoming
    if held != incoming:
        raise BotError(
            "another Level-2 brain already holds this session",
            409,
            BOT_REASON_BRAIN_EXCLUSIVE,
        )
    return incoming


def reset_for_tests() -> None:
    persist.reset_for_tests()
