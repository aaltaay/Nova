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
from bot.session import clamp_caps
from constants_bot import (
    BOT_LEVEL_EYES,
    BOT_LEVEL_OFF,
    BOT_LEVEL_STRATEGY,
    BOT_LEVEL_UNRESTRICTED,
    BOT_REASON_ARM_REQUIRED,
    BOT_REASON_L3_PARKED,
    BOT_REASON_SETUP_NO_SCANNER,
    BOT_SETUPS,
    BOT_SETUPS_WITH_SCANNER,
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


def _validate_setup(name: str) -> str:
    """One setup plays at a time, and only one with a live scanner can (ADR 027, ADR 031)."""
    if name not in BOT_SETUPS:
        raise BotError(f"unknown setup {name!r}", 400)
    if name not in BOT_SETUPS_WITH_SCANNER:
        raise BotError(
            f"{name} has no scanner yet -- it cannot be played until it has one and its read-out passes",
            400,
            BOT_REASON_SETUP_NO_SCANNER,
        )
    return name


def apply_patch(
    body: dict[str, Any],
    *,
    desk: bool = True,
    arm_token: str | None = None,
) -> dict[str, Any]:
    """Desk/strategy controls. Raising above L1 needs a desk arm token."""
    row = load_session()
    level_before = int(row.get("level") or BOT_LEVEL_OFF)
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
            from bot.gates import readout_open

            if not readout_open():
                # ADR 027: Strategy can be chosen before its read-out passes, but
                # on Live it lands not active -- the bot proposes like Eyes until
                # then. Paper and Sim skip the read-out (ADR 030).
                clear_arm_fields(row)
    if "setup" in body:
        from bot.setup_levels import on_choose

        new = _validate_setup(str(body.get("setup") or ""))
        old = row.get("setup")
        if on_choose(row, new):
            # ADR 031: a different setup is a new decision -- the bot stops; Activate again.
            clear_arm_fields(row)
            _audit_setup(old, new, deactivated=True)
        elif new != old:
            _audit_setup(old, new, deactivated=False)
        row["setup"] = new
    if "setup_levels" in body:
        from bot.setup_levels import apply as apply_setup_levels

        apply_setup_levels(row, body.get("setup_levels"))
    if "breakers" in body:
        from bot.breaker_limits import apply as apply_breakers
        from bot.gates import current_venue

        changed = apply_breakers(row, body.get("breakers"), current_venue())
        if changed is not None:
            _audit_breakers(*changed)
    if "symbol_allowlist" in body:
        row["symbol_allowlist"] = normalize_symbols(body.get("symbol_allowlist"))
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
    if body.get("reenable") and desk:
        row["soft_breaker_fired"] = False
    saved = save_session(row)
    if level_before != int(saved.get("level") or BOT_LEVEL_OFF):
        _audit_level(level_before, saved)
    return saved


def _audit_level(before: int, row: dict[str, Any]) -> None:
    """The Bots page timeline shows who moved the level (ADR 027)."""
    from bot.audit import record

    try:
        record(action="level", outcome=f"{before}->{int(row.get('level') or 0)}",
               reason=None if row.get("armed") or int(row.get("level") or 0) < BOT_LEVEL_STRATEGY
               else "Strategy lands not active on Live until the read-out passes",
               inputs={"from": before, "to": int(row.get("level") or 0)})
    except Exception:
        import logging

        logging.getLogger(__name__).warning("bot audit: level change not recorded", exc_info=True)


def _audit_breakers(venue: str, before: dict, after: dict) -> None:
    """The timeline shows every change to a venue's loss breakers (operator ask 2026-09-24)."""
    from bot.audit import record

    try:
        record(action="breakers", outcome=venue,
               reason=(f"{venue}: bot trip {before['soft_usd']:g} -> {after['soft_usd']:g}, "
                       f"all-stop {before['hard_usd']:g} -> {after['hard_usd']:g}"),
               inputs={"venue": venue, "before": before, "after": after})
    except Exception:
        import logging

        logging.getLogger(__name__).warning("bot audit: breaker change not recorded", exc_info=True)


def _audit_setup(before: Any, after: str, *, deactivated: bool) -> None:
    """The Bots page timeline shows who changed the setup that plays (ADR 031)."""
    from bot.audit import record

    try:
        record(action="setup", outcome=f"{before or '?'}->{after}",
               reason="the bot stopped: a different setup is a new decision -- Activate again" if deactivated
               else None, inputs={"from": before, "to": after, "deactivated": deactivated})
    except Exception:
        import logging

        logging.getLogger(__name__).warning("bot audit: setup change not recorded", exc_info=True)


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
    from bot.gates import assert_readout_open

    assert_readout_open()
    if not is_desk_active(current):
        raise BotError(
            "desk is Not active -- Activate before live fire",
            409,
            BOT_REASON_NOT_ACTIVE,
        )
    from ibkr.trading_allowed import require_places_allowed

    require_places_allowed()
    assert_fresh_heartbeat(current)
    return current
