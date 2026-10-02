"""Bot session snapshot + exclusive L2 brain claim.

``public_view`` is ``GET /api/bot/session`` (ADR 042's wire contract): the desk venue's
dial -- the master ``level``, each setup's own and effective level, the sleeve, the bot's
stocks, the trips and the lock -- with ``active`` / ``ready`` and every gate and its reason.
"""
from __future__ import annotations

import logging
from typing import Any

from bot import persist
from bot.arming import has_desk_arm, heartbeat_is_fresh, is_desk_active
from bot.clock import soft_latched
from bot.eligibility import normalize_symbols
from bot.errors import BotError
from constants_bot import (
    BOT_LEVEL_STRATEGY,
    BOT_REASON_ARM_REQUIRED,
    BOT_REASON_BRAIN_EXCLUSIVE,
    BOT_SETUPS,
    BOT_SETUPS_WITH_SCANNER,
)

logger = logging.getLogger(__name__)


def get_session() -> dict[str, Any]:
    row = persist.load_session()
    return public_view(row)


def public_view(row: dict[str, Any]) -> dict[str, Any]:
    from bot import activation, sleeve, switch
    from bot.gates import day_lock, first_closed, gates
    from bot.setup_levels import effective, master, own_levels
    from ibkr.trading_allowed import places_allowed

    level = master(row)
    venue_now = activation.venue_state()
    venue = venue_now[0]
    active = is_desk_active(row)
    brain_id = row.get("brain_session_id") if level >= BOT_LEVEL_STRATEGY else None
    alive = heartbeat_is_fresh(row) and bool(brain_id)
    places_ok, places_reason = places_allowed()
    own, eff = own_levels(row), effective(row)
    gate_list = gates(row, venue_now)
    closed = first_closed(gate_list)
    ready = active and closed is None
    ready_reason = None if ready else ("the bot is not active: turn the Bot switch on" if not active
                                       else str(closed["detail"].get("text") or closed["id"]))
    caps = sleeve.view(row.get("caps"), venue)
    lock = day_lock(row, venue)
    daily = next((g["detail"] for g in gate_list if g["id"] == "daily_cap"), {})
    tripped = soft_latched(row)
    return {
        "level": level,
        "active": active,
        # ADR 043: the Bot switch -- ON is the master at Strategy and Active; why it is off, the trip's latch.
        **switch.view(row, venue),
        "armed": active,                         # LEGACY alias of ``active`` (one release)
        "has_desk_arm": has_desk_arm(row),
        "deactivated": _deactivated(row.get("deactivated")),
        # ADR 042: every setup with a scanner has its own level; effective = min(master, own).
        "setups": [{"id": sid, "scanner": sid in BOT_SETUPS_WITH_SCANNER,
                    "level": own.get(sid) if sid in BOT_SETUPS_WITH_SCANNER else None,
                    "effective": eff.get(sid) if sid in BOT_SETUPS_WITH_SCANNER else None} for sid in BOT_SETUPS],
        "setup_levels": dict(own),
        "ready": ready,
        "ready_reason": ready_reason,
        "live_fire_ready": ready,                # LEGACY alias of ``ready`` (one release)
        "gates": gate_list,
        "caps": caps,
        "caps_bounds": sleeve.bounds(),
        "caps_by_venue": sleeve.by_venue(row),
        "symbol_allowlist": normalize_symbols(row.get("symbol_allowlist")),
        "entries_today": _entries_today(venue, daily),
        "brain_session_id": brain_id,
        "brain_heartbeat_ts": row.get("brain_heartbeat_ts") if brain_id else None,
        "brain_alive": alive,
        "trading_allowed": places_ok,
        "trading_allowed_reason": None if places_ok else places_reason or None,
        "soft_breaker_fired": tripped,
        "soft_breaker": {"fired": tripped, "at": row.get("soft_breaker_at"), "pnl": row.get("soft_breaker_pnl"),
                         "until": row.get("soft_breaker_until")},
        # The loss breakers' thresholds, per venue (operator ask 2026-09-24).
        "breakers": _breakers_view(row, venue),
        # The dial is per venue too (operator report 2026-09-30): ``level`` is the desk's own.
        "level_venue": row.get("level_venue"),
        "levels_by_venue": _levels_by_venue(row),
        "day_lock": lock,
        "day_locks": _day_locks(row),
        "hard_lock_until_date": lock.get("until"),       # LEGACY (this venue's)
        "day_lock_active": bool(lock.get("active")),     # LEGACY (this venue's)
        "focus": list(row.get("focus") or []),
        "trader_live": list(row.get("trader_live") or []),
        "working": list(row.get("working") or []),
        # Nova's own bot (ADR 030, 042): whether it plays, and its current or last trade.
        "runner": _runner_view(row),
        "trade": _trade_view(row.get("trade"), venue),
        # Sim time travel (ADR 020): the last scratch-account unwind this
        # process published, so a polling bot re-reads the ledger after it.
        "last_rewind": _last_rewind(),
        "updated_ts": row.get("updated_ts"),
    }


def _deactivated(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {"at": value.get("at"), "reason": value.get("reason"), "text": value.get("text")}


def _entries_today(venue: str | None, daily: dict[str, Any]) -> dict[str, Any]:
    """``{count, cap, venue_day, entries, approved}`` -- the shared Nova count (ADR 042 E)."""
    from bot import entry_rules

    try:
        out = entry_rules.today(venue, cap=int(daily.get("cap") or 0) or None)
    except Exception:
        # Said on the page, never read as zero; the exception itself stays in the log (CodeQL: no
        # exception text in an API answer).
        logger.warning("bot session: the day's Nova entries could not be counted", exc_info=True)
        return {"count": None, "cap": daily.get("cap"), "venue_day": None, "entries": [], "approved": None,
                "error": "the day's entries could not be counted (the backend log has the error)"}
    return out


def _breakers_view(row: dict[str, Any], venue: str | None) -> dict[str, Any]:
    from bot.breaker_limits import view

    out = dict(view(row, venue))
    out.setdefault("note", None)
    return out


def _levels_by_venue(row: dict[str, Any]) -> dict[str, int]:
    from bot.venue_levels import by_venue

    return by_venue(row)


def _day_locks(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from bot.gates import day_lock
    from constants_bot import BOT_BREAKER_VENUES

    return {v: day_lock(row, v) for v in BOT_BREAKER_VENUES}


def _trade_view(trade: Any, venue: str | None) -> dict[str, Any] | None:
    if not isinstance(trade, dict):
        return None
    from bot.first_pullback.runner import waiting_text

    out = dict(trade)
    out["waiting"] = waiting_text(out, venue)
    return out


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


def require_l2_brain(brain_session_id: str | None, *, claim: bool = True) -> str:
    row = persist.load_session()
    if int(row.get("level") or 0) != BOT_LEVEL_STRATEGY:
        raise BotError("L2 brain required only at Strategy level", 409, BOT_REASON_BRAIN_EXCLUSIVE)
    desk_token = (row.get("desk_arm_token") or "").strip()
    if not is_desk_active(row):
        raise BotError(
            "Activate on the Bots page before a brain can claim",
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
