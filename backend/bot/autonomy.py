"""L0 / L1 / L2 transitions. L3 is parked."""
from __future__ import annotations

from typing import Any

from bot.arming import (
    assert_fresh_heartbeat,
    clear_arm_fields,
    is_desk_active,
    issue_arm_token,
    require_matching_arm_token,
)
from bot.errors import BotError
from bot.persist import load_session, save_session
from bot.eligibility import normalize_symbols
from bot.packs import default_pack_settings, normalize_pack
from bot.session import clamp_caps
from constants_bot import (
    BOT_LEVEL_EYES,
    BOT_LEVEL_OFF,
    BOT_LEVEL_STRATEGY,
    BOT_LEVEL_UNRESTRICTED,
    BOT_REASON_ARM_REQUIRED,
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


def apply_patch(
    body: dict[str, Any],
    *,
    desk: bool = True,
    arm_token: str | None = None,
) -> dict[str, Any]:
    """Desk/strategy controls. Raising above L1 needs a desk arm token."""
    row = load_session()
    if "armed" in body:
        raise BotError(
            "armed is desk Activate/Stop only -- POST /api/bot/session/arm or /disarm",
            400,
            BOT_REASON_ARM_REQUIRED,
        )
    if "level" in body:
        level = _validate_level(int(body["level"]))
        current = int(row.get("level") or BOT_LEVEL_OFF)
        if level > BOT_LEVEL_EYES and level > current:
            require_matching_arm_token(row, arm_token)
        row["level"] = level
        if level < BOT_LEVEL_STRATEGY:
            leaving_strategy = current >= BOT_LEVEL_STRATEGY
            if level == BOT_LEVEL_OFF or leaving_strategy:
                clear_arm_fields(row)
            else:
                row["brain_session_id"] = None
                row["claim_arm_token"] = None
                row["brain_heartbeat_ts"] = None
            if level == BOT_LEVEL_OFF:
                row["strategy"] = None
        if level == BOT_LEVEL_STRATEGY:
            row["strategy"] = row.get("strategy") or BOT_STRATEGY_SMALL_CAP
            row["active_pack"] = normalize_pack(row.get("active_pack"))
    if "active_pack" in body:
        row["active_pack"] = normalize_pack(str(body.get("active_pack")))
    if "symbol_allowlist" in body:
        row["symbol_allowlist"] = normalize_symbols(body.get("symbol_allowlist"))
    if "pack_settings" in body and isinstance(body["pack_settings"], dict):
        settings = default_pack_settings()
        settings.update(dict(row.get("pack_settings") or {}))
        incoming = body["pack_settings"]
        for key, value in incoming.items():
            if isinstance(value, dict):
                merged = dict(settings.get(key) or {})
                merged.update(value)
                settings[key] = merged
        row["pack_settings"] = settings
    if "strategy" in body and int(row.get("level") or 0) >= BOT_LEVEL_STRATEGY:
        name = str(body.get("strategy") or "").strip()
        if name and name not in BOT_STRATEGIES:
            raise BotError(f"unknown strategy {name!r} -- first L2 strategy is small-cap", 400)
        row["strategy"] = name or BOT_STRATEGY_SMALL_CAP
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
    if "llm" in body and isinstance(body["llm"], dict):
        from bot.llm_guard import default_llm

        llm = {**default_llm(), **dict(row.get("llm") or {})}
        patch = body["llm"]
        if "usd_cap" in patch:
            llm["usd_cap"] = max(0.0, float(patch["usd_cap"]))
        if "call_cap" in patch:
            llm["call_cap"] = max(0, int(patch["call_cap"]))
        row["llm"] = llm
    if body.get("reenable") and desk:
        row["soft_breaker_fired"] = False
    return save_session(row)


def apply_desk_level(level: int, **extra: Any) -> dict[str, Any]:
    """Internal/tests: Activate then set level. HTTP never uses this shortcut."""
    token = issue_arm_token() if int(level) > BOT_LEVEL_EYES else None
    return apply_patch({"level": level, **extra}, desk=True, arm_token=token)


def drop_to_l0(*, keep_soft_latch: bool = True) -> dict[str, Any]:
    row = load_session()
    row["level"] = BOT_LEVEL_OFF
    clear_arm_fields(row)
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
    from constants_bot import BOT_REASON_L1_NO_FIRE, BOT_REASON_NOT_ACTIVE

    current = assert_not_dark(row)
    if int(current.get("level") or 0) < BOT_LEVEL_STRATEGY:
        raise BotError(
            "Level 1 Eyes cannot place, cancel, or flatten -- human places",
            409,
            BOT_REASON_L1_NO_FIRE,
        )
    if not is_desk_active(current):
        raise BotError(
            "desk is Not active -- Activate before live fire",
            409,
            BOT_REASON_NOT_ACTIVE,
        )
    assert_fresh_heartbeat(current)
    return current
