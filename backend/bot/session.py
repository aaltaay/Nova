"""Bot session snapshot + exclusive L2 brain claim."""
from __future__ import annotations

from typing import Any

from bot import persist
from bot.arming import has_desk_arm, heartbeat_is_fresh, is_desk_active
from bot.clock import lock_is_active
from bot.eligibility import normalize_symbols
from bot.errors import BotError
from bot.kinds import default_allowlist
from constants_bot import (
    BOT_ADVISE_DEFAULT_CALL_CAP,
    BOT_ADVISE_DEFAULT_USD_CAP,
    BOT_BP_BUDGET_HARD_MAX_USD,
    BOT_LEVEL_OFF,
    BOT_LEVEL_STRATEGY,
    BOT_MAX_SHARES_CAP,
    BOT_REASON_ARM_REQUIRED,
    BOT_REASON_BRAIN_EXCLUSIVE,
    BOT_SETUP_DEFAULT,
    BOT_SETUPS,
    BOT_SETUPS_WITH_SCANNER,
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
    token_on = has_desk_arm(row)
    armed = is_desk_active(row)
    brain_id = row.get("brain_session_id") if level >= BOT_LEVEL_STRATEGY else None
    alive = heartbeat_is_fresh(row) and bool(brain_id)
    from ibkr.trading_allowed import places_allowed

    places_ok, places_reason = places_allowed()
    from bot.gates import gates, readout, readout_required

    out = readout()
    required = readout_required()
    return {
        "level": level,
        "armed": armed,
        "has_desk_arm": token_on,
        "strategy": row.get("strategy") if level >= BOT_LEVEL_STRATEGY else None,
        # ADR 027: the operator's playbook; one setup plays at a time.
        "setup": row.get("setup") or BOT_SETUP_DEFAULT,
        "setups": [{"id": sid, "scanner": sid in BOT_SETUPS_WITH_SCANNER} for sid in BOT_SETUPS],
        "readout": out,
        # ADR 030: Live waits on the read-out; Paper and Sim do not.
        "readout_required": required,
        "gates": gates(row),
        "symbol_allowlist": normalize_symbols(row.get("symbol_allowlist")),
        "brain_session_id": brain_id,
        "brain_heartbeat_ts": row.get("brain_heartbeat_ts") if brain_id else None,
        "brain_alive": alive,
        "trading_allowed": places_ok,
        "trading_allowed_reason": None if places_ok else places_reason or None,
        "live_fire_ready": (
            level >= BOT_LEVEL_STRATEGY
            and armed
            and alive
            and bool(brain_id)
            and places_ok
            and (bool(out.get("passed")) or not required)
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
        "soft_breaker_fired": bool(row.get("soft_breaker_fired")),
        "hard_lock_until_date": lock_until,
        "day_lock_active": lock_is_active(lock_until),
        "focus": list(row.get("focus") or []),
        "trader_live": list(row.get("trader_live") or []),
        "working": list(row.get("working") or []),
        # ADR 030: Nova's own first-pullback bot -- whether it plays, and its current or last trade.
        "runner": _runner_view(row),
        "trade": _trade_view(row.get("trade")),
        # Sim time travel (ADR 020): the last scratch-account unwind this
        # process published, so a polling bot re-reads the ledger after it.
        "last_rewind": _last_rewind(),
        "updated_ts": row.get("updated_ts"),
    }


def _trade_view(trade: Any) -> dict[str, Any] | None:
    return dict(trade) if isinstance(trade, dict) else None


def _runner_view(row: dict[str, Any]) -> dict[str, Any]:
    from bot.first_pullback.runner import status

    return status(row)


def _last_rewind() -> dict[str, Any] | None:
    from bot.rewind import last

    return last()


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
    if not is_desk_active(row):
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
