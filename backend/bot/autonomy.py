"""L0 / L1 / L2 transitions. L3 is parked."""
from __future__ import annotations

from typing import Any

from bot.errors import BotError
from bot.persist import load_session, save_session
from bot.session import clamp_caps
from constants_bot import (
    BOT_LEVEL_EYES,
    BOT_LEVEL_OFF,
    BOT_LEVEL_STRATEGY,
    BOT_LEVEL_UNRESTRICTED,
    BOT_REASON_L3_PARKED,
    BOT_STRATEGIES,
    BOT_STRATEGY_SMALL_CAP,
)


def _validate_level(level: int) -> int:
    if level == BOT_LEVEL_UNRESTRICTED:
        raise BotError(
            "L3 Unrestricted is parked until L0-L2 small-cap is proven (#216)",
            409,
            BOT_REASON_L3_PARKED,
        )
    if level not in (BOT_LEVEL_OFF, BOT_LEVEL_EYES, BOT_LEVEL_STRATEGY):
        raise BotError(f"unknown autonomy level {level}", 400)
    return level


def apply_patch(body: dict[str, Any], *, desk: bool = True) -> dict[str, Any]:
    """Desk/strategy controls. Brain cannot raise L3 or bypass exclusive claim."""
    row = load_session()
    if "level" in body:
        level = _validate_level(int(body["level"]))
        row["level"] = level
        if level < BOT_LEVEL_STRATEGY:
            row["armed"] = False
            row["brain_session_id"] = None
            if level == BOT_LEVEL_OFF:
                row["strategy"] = None
        if level == BOT_LEVEL_STRATEGY:
            row["strategy"] = row.get("strategy") or BOT_STRATEGY_SMALL_CAP
            row["armed"] = True
    if "strategy" in body and int(row.get("level") or 0) >= BOT_LEVEL_STRATEGY:
        name = str(body.get("strategy") or "").strip()
        if name and name not in BOT_STRATEGIES:
            raise BotError(f"unknown strategy {name!r} -- first L2 strategy is small-cap", 400)
        row["strategy"] = name or BOT_STRATEGY_SMALL_CAP
    if "armed" in body and desk:
        row["armed"] = bool(body["armed"]) and int(row.get("level") or 0) >= BOT_LEVEL_STRATEGY
    if "caps" in body and isinstance(body["caps"], dict):
        caps = dict(row.get("caps") or {})
        caps.update(body["caps"])
        row["caps"] = clamp_caps(caps)
    if "advise" in body and isinstance(body["advise"], dict):
        advise = dict(row.get("advise") or {})
        patch = body["advise"]
        if "enabled" in patch:
            advise["enabled"] = bool(patch["enabled"])
        if "usd_cap" in patch:
            advise["usd_cap"] = max(0.0, float(patch["usd_cap"]))
        if "call_cap" in patch:
            advise["call_cap"] = max(0, int(patch["call_cap"]))
        row["advise"] = advise
    if body.get("reenable") and desk:
        row["soft_breaker_fired"] = False
    return save_session(row)


def drop_to_l0(*, keep_soft_latch: bool = True) -> dict[str, Any]:
    row = load_session()
    row["level"] = BOT_LEVEL_OFF
    row["armed"] = False
    row["brain_session_id"] = None
    row["strategy"] = None
    row["bot_qty"] = {}
    row["working"] = []
    if keep_soft_latch:
        row["soft_breaker_fired"] = True
    return save_session(row)


def assert_not_dark(row: dict[str, Any] | None = None) -> dict[str, Any]:
    from constants_bot import BOT_REASON_L0_DARK

    current = row or load_session()
    if int(current.get("level") or 0) <= BOT_LEVEL_OFF:
        raise BotError("bot is Level 0 -- fully dark", 409, BOT_REASON_L0_DARK)
    return current


def assert_can_fire(row: dict[str, Any] | None = None) -> dict[str, Any]:
    from constants_bot import BOT_REASON_L1_NO_FIRE

    current = assert_not_dark(row)
    if int(current.get("level") or 0) < BOT_LEVEL_STRATEGY or not current.get("armed"):
        raise BotError(
            "Level 1 Eyes cannot place, cancel, or flatten -- human places",
            409,
            BOT_REASON_L1_NO_FIRE,
        )
    return current
