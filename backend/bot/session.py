"""Bot session snapshot + exclusive L2 brain claim.

``public_view`` is ``GET /api/bot/session`` (ADR 042's wire contract, trimmed by ADR 072): the desk venue's dial --
the master ``level``, each setup's own and effective level (every strategy watches: Eyes), the sleeve the desk's risk
per trade is read from, the bot's stocks -- and the brain's claim. ADR 072 retired the Bot switch, the family keys,
Activate's gates, the strategy bot's trade and its entry count, so their fields left the answer.
"""
from __future__ import annotations

import logging
from typing import Any

from bot import persist
from bot.arming import heartbeat_is_fresh, is_desk_active
from bot.eligibility import normalize_symbols
from bot.errors import BotError
from constants_bot import (
    BOT_BRAIN_DOOR_CLOSED_TEXT,
    BOT_LEVEL_STRATEGY,
    BOT_REASON_ARM_REQUIRED,
    BOT_REASON_BRAIN_EXCLUSIVE,
    BOT_SETUPS,
    BOT_SETUPS_WITH_SCANNER,
)

logger = logging.getLogger(__name__)


def short_view(setup: str) -> dict[str, Any]:
    """ADR 049: every setup's ``side`` and a short's informative five-year ``test``. #847: a watch-only
    setup's ``watch_only`` is true and its On is locked, saying why."""
    from bot.setup_levels import on_lock
    from constants_bot import SIDE_SHORT, setup_side, watch_only

    side = setup_side(setup)
    if watch_only(setup):
        return {"side": side, "test": None, "locked": on_lock(setup), "watch_only": True}
    if side != SIDE_SHORT:
        return {"side": side, "test": None, "locked": None}
    from setup_scanner import short_tests

    return {"side": side, "test": short_tests.test_in_play(setup), "locked": None}


def get_session() -> dict[str, Any]:
    row = persist.load_session()
    return public_view(row)


def public_view(row: dict[str, Any]) -> dict[str, Any]:
    from bot import sleeve
    from bot.door import current_venue
    from bot.setup_levels import effective, master, own_levels
    from bot.venue_levels import by_venue
    from ibkr.trading_allowed import places_allowed

    level = master(row)
    venue = current_venue()
    brain_id = row.get("brain_session_id") if level >= BOT_LEVEL_STRATEGY else None
    alive = heartbeat_is_fresh(row) and bool(brain_id)
    places_ok, places_reason = places_allowed()
    own, eff = own_levels(row), effective(row)
    return {
        "level": level,
        "active": is_desk_active(row),
        # ADR 042: every setup with a scanner has its own level; ADR 072: each reads Eyes -- every strategy watches.
        "setups": [{"id": sid, "scanner": sid in BOT_SETUPS_WITH_SCANNER,
                    "level": own.get(sid) if sid in BOT_SETUPS_WITH_SCANNER else None,
                    "effective": eff.get(sid) if sid in BOT_SETUPS_WITH_SCANNER else None,
                    **short_view(sid)} for sid in BOT_SETUPS],
        "setup_levels": dict(own),
        "caps": sleeve.view(row.get("caps"), venue),
        "caps_bounds": sleeve.bounds(),
        "caps_by_venue": sleeve.by_venue(row),
        "symbol_allowlist": normalize_symbols(row.get("symbol_allowlist")),
        "brain_session_id": brain_id,
        "brain_heartbeat_ts": row.get("brain_heartbeat_ts") if brain_id else None,
        "brain_alive": alive,
        "trading_allowed": places_ok,
        "trading_allowed_reason": None if places_ok else places_reason or None,
        # The dial is per venue too (operator report 2026-09-30): ``level`` is the desk's own.
        "level_venue": row.get("level_venue"),
        "levels_by_venue": by_venue(row),
        "focus": list(row.get("focus") or []),
        "trader_live": list(row.get("trader_live") or []),
        "working": list(row.get("working") or []),
        # Sim time travel (ADR 020): the last scratch-account unwind this
        # process published, so a polling bot re-reads the ledger after it.
        "last_rewind": _last_rewind(),
        # The day cover's alarms (ADR 048 decision 5): every desk window polls them here, so a short Nova could not
        # cover at 15:55 is shouted on every screen. They outlive the bots (ADR 072): the cover is the desk's.
        "shorts": _shorts(),
        "updated_ts": row.get("updated_ts"),
    }


def _shorts() -> dict[str, Any]:
    """``{day_cover: {alarms}}`` -- memory reads only, never a wait on IBKR."""
    from short_sale import cover_alarm

    try:
        return {"day_cover": cover_alarm.view()}
    except Exception:
        # The exception's own text stays in the log: the read goes to every window, never a stack detail (CodeQL).
        logger.warning("bot: the day cover's alarms could not be read", exc_info=True)
        return {"day_cover": {"alarms": []}, "error": "the day cover's alarms could not be read -- see the backend log"}


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
        raise BotError(BOT_BRAIN_DOOR_CLOSED_TEXT, 409, BOT_REASON_ARM_REQUIRED)
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
