"""L0 / L1 / L2 transitions (L3 is parked) and the desk's configuration patch (ADR 042).

``level`` is the master ceiling and ``setup_levels`` each setup's own (``bot.setup_levels``);
raising either is configuration, not "go": it needs no Activate token. Lowering the master
below Strategy, or leaving no setup at Strategy, deactivates an active bot and says why
(``bot.activation``). The bot's stock list is not written here: it goes through
``stock_mode`` (``bot.allowlist``), whose rules every desk button meets.
"""
from __future__ import annotations

import logging
from typing import Any

from bot.arming import assert_fresh_heartbeat, is_desk_active, issue_arm_token
from bot.errors import BotError
from bot.persist import load_session, save_session
from constants_bot import (
    BOT_LEVEL_EYES,
    BOT_LEVEL_OFF,
    BOT_LEVEL_STRATEGY,
    BOT_LEVEL_UNRESTRICTED,
    BOT_REASON_ARM_REQUIRED,
    BOT_REASON_L3_PARKED,
    BOT_REASON_SETUP_RETIRED,
    BOT_SETUP_RETIRED_TEXT,
)

logger = logging.getLogger(__name__)


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
    """Desk controls: the master level, each setup's level, the sleeve, the breakers, re-enable.

    ``arm_token`` is accepted and ignored (configuration needs no Activate token, ADR 042)."""
    del arm_token
    from bot import activation
    from bot.setup_levels import at_strategy

    if "armed" in body:
        raise BotError(
            "armed is Activate / Deactivate only -- POST /api/bot/session/arm or /disarm",
            400,
            BOT_REASON_ARM_REQUIRED,
        )
    if "setup" in body:
        raise BotError(BOT_SETUP_RETIRED_TEXT, 400, BOT_REASON_SETUP_RETIRED)
    if "symbol_allowlist" in body:
        raise BotError("the bot's stocks are set through Who trades (stock mode) -- "
                       "PATCH /api/bot/session routes them there", 400, BOT_REASON_ARM_REQUIRED)
    row = load_session()
    level_before = int(row.get("level") or BOT_LEVEL_OFF)
    was_active = is_desk_active(row)
    changes: list[tuple[str, Any]] = []
    if "level" in body:
        level = _validate_level(int(body["level"]))
        row["level"] = level
        if level < BOT_LEVEL_STRATEGY:
            # The claim of an external brain cannot outlive Strategy.
            row["brain_session_id"] = None
            row["claim_arm_token"] = None
            row["brain_heartbeat_ts"] = None
    if "setup_levels" in body:
        from bot.setup_levels import apply as apply_setup_levels

        for sid, (before, after) in sorted(apply_setup_levels(row, body.get("setup_levels")).items()):
            changes.append(("setup_level", (sid, before, after)))
    if "breakers" in body:
        from bot.breaker_limits import apply as apply_breakers
        from bot.gates import current_venue

        changed = apply_breakers(row, body.get("breakers"), current_venue())
        if changed is not None:
            changes.append(("breakers", changed))
    if "caps" in body and isinstance(body["caps"], dict):
        changes.extend(("caps", c) for c in _apply_caps(row, body["caps"]))
    if body.get("reenable") and desk:
        row["soft_breaker_fired"] = False
        row["soft_breaker_until"] = None
    deactivated = None
    if was_active:
        if "level" in body and int(row.get("level") or BOT_LEVEL_OFF) < BOT_LEVEL_STRATEGY:
            deactivated = "level"
        elif ("level" in body or "setup_levels" in body) and not at_strategy(row):
            deactivated = "no_setup"
        if deactivated:
            activation.deactivate(row, deactivated)
    saved = save_session(row)
    if level_before != int(saved.get("level") or BOT_LEVEL_OFF):
        _audit_level(level_before, saved)
    for kind, change in changes:
        if kind == "setup_level":
            _audit_setup_level(*change)
        elif kind == "breakers":
            _audit_breakers(*change)
        else:
            _audit_caps(*change)
    if deactivated:
        activation.record(deactivated)
    return saved


def _apply_caps(row: dict[str, Any], patch: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """``PATCH {caps: {venue?, ...}}``: the named venue's sleeve (default: the desk's)."""
    from bot.gates import current_venue
    from bot.sleeve import apply as apply_sleeve
    from bot.venue_levels import dial_of, put
    from constants_bot import BOT_BREAKER_VENUES, BOT_REASON_CAPS_INVALID

    venue = patch.get("venue") or current_venue()
    if venue not in BOT_BREAKER_VENUES:
        raise BotError(f"caps.venue is one of {', '.join(BOT_BREAKER_VENUES)}", 400, BOT_REASON_CAPS_INVALID)
    current = row.get("caps") if venue == row.get("level_venue") or row.get("level_venue") is None \
        else dial_of(row, venue).get("caps")
    after, changed = apply_sleeve(current, patch)
    if row.get("level_venue") is None or venue == row.get("level_venue"):
        row["caps"] = after
    else:
        put(row, venue, "caps", after)
    return [(venue, changed)] if changed else []


def _audit_level(before: int, row: dict[str, Any]) -> None:
    """The Bots page timeline shows who moved the master level (ADR 027, 042)."""
    from bot.audit import record

    after = int(row.get("level") or 0)
    try:
        record(action="level", outcome=f"{before}->{after}",
               reason=("the master ceiling: setups do at most this" if after >= BOT_LEVEL_STRATEGY
                       else "the master ceiling is below Strategy: no setup trades"),
               inputs={"from": before, "to": after})
    except Exception:
        logger.warning("bot audit: level change not recorded", exc_info=True)


def _audit_breakers(venue: str, before: dict, after: dict) -> None:
    """The timeline shows every change to a venue's loss breakers (operator ask 2026-09-24)."""
    from bot.audit import record

    try:
        record(action="breakers", outcome=venue,
               reason=(f"{venue}: bot trip {before['soft_usd']:g} -> {after['soft_usd']:g}, "
                       f"all-stop {before['hard_usd']:g} -> {after['hard_usd']:g}"),
               inputs={"venue": venue, "before": before, "after": after})
    except Exception:
        logger.warning("bot audit: breaker change not recorded", exc_info=True)


def _audit_caps(venue: str, changed: dict[str, tuple[Any, Any]]) -> None:
    """The timeline shows every change to a venue's sleeve (ADR 042 E)."""
    from bot.audit import record

    try:
        record(action="caps", outcome=venue,
               reason=f"{venue} sleeve: " + ", ".join(f"{k} {a!r} -> {b!r}" for k, (a, b) in sorted(changed.items())),
               inputs={"venue": venue, "changed": {k: {"from": a, "to": b} for k, (a, b) in changed.items()}})
    except Exception:
        logger.warning("bot audit: sleeve change not recorded", exc_info=True)


def _audit_setup_level(setup: str, before: int, after: int) -> None:
    """The timeline shows a setup's own level change on its card (ADR 031, 042)."""
    from bot.audit import record

    said = {BOT_LEVEL_STRATEGY: "Strategy: the bot may trade its go triggers while Active",
            BOT_LEVEL_EYES: "Eyes: it proposes on near + go",
            BOT_LEVEL_OFF: "Off: it watches and scores in silence"}
    try:
        record(action="setup_level", outcome=f"{setup}:{before}->{after}", reason=said.get(after),
               inputs={"setup": setup, "from": before, "to": after})
    except Exception:
        logger.warning("bot audit: setup level change not recorded", exc_info=True)


def apply_desk_level(level: int, **extra: Any) -> dict[str, Any]:
    """Internal/tests: set the master level (at Strategy with the first pullback at Strategy unless
    ``setup_levels`` says otherwise), then turn Activate on without its rules (``bot.activation``)."""
    if int(level) >= BOT_LEVEL_STRATEGY:
        extra.setdefault("setup_levels", {"first_pullback": BOT_LEVEL_STRATEGY})
    saved = apply_patch({"level": level, **extra}, desk=True)
    if int(level) >= BOT_LEVEL_STRATEGY:
        issue_arm_token()
    return load_session() if int(level) >= BOT_LEVEL_STRATEGY else saved


def drop_to_eyes(*, keep_soft_latch: bool = True, reason: str = "bot_trip") -> dict[str, Any]:
    """A loss breaker tripped: the bot is off, the way the Bot switch's OFF leaves it (ADR 044) -- the
    master at Eyes, so the setups at Eyes or On keep proposing; Activate cleared (``reason``:
    ``bot_trip`` or ``all_stop``), the bot's orders forgotten, the bot trip latched until 04:00 ET."""
    from bot import activation

    row = load_session()
    row["level"] = BOT_LEVEL_EYES
    was = activation.deactivate(row, reason)
    row["bot_qty"] = {}
    row["working"] = []
    if keep_soft_latch:
        from bot.clock import lock_until_date

        row["soft_breaker_fired"] = True
        row["soft_breaker_until"] = lock_until_date()
    saved = save_session(row)
    if was:
        activation.record(reason)
    return saved


# The name the breakers and tests knew (ADR 032); since ADR 044 it drops to Eyes, not Off.
drop_to_l0 = drop_to_eyes


def assert_not_dark(row: dict[str, Any] | None = None) -> dict[str, Any]:
    from constants_bot import BOT_REASON_L0_DARK

    current = row or load_session()
    if int(current.get("level") or 0) <= BOT_LEVEL_OFF:
        raise BotError("bot is Level 0 -- fully dark", 409, BOT_REASON_L0_DARK)
    return current


def assert_not_live() -> None:
    """J (ADR 042): Nova's bot -- and the localhost bot API -- never touch Live or a replay desk."""
    from bot.activation import venue_block, venue_state
    from constants_bot import BOT_LIVE_NOT_BUILT_TEXT, BOT_REASON_LIVE_NOT_BUILT

    venue, edge, readable = venue_state()
    blocked = venue_block(venue, edge, readable)
    if blocked is not None:
        raise BotError(BOT_LIVE_NOT_BUILT_TEXT if blocked[0] == BOT_REASON_LIVE_NOT_BUILT
                       else f"{BOT_LIVE_NOT_BUILT_TEXT} ({blocked[1]})", 409, BOT_REASON_LIVE_NOT_BUILT)


def assert_can_fire(row: dict[str, Any] | None = None) -> dict[str, Any]:
    from constants_bot import BOT_REASON_L1_NO_FIRE, BOT_REASON_NOT_ACTIVE
    from ibkr.trading_allowed import require_places_allowed

    assert_not_live()
    current = assert_not_dark(row)
    if int(current.get("level") or 0) < BOT_LEVEL_STRATEGY:
        raise BotError(
            "Level 1 Eyes cannot place, cancel, or flatten -- human places",
            409,
            BOT_REASON_L1_NO_FIRE,
        )
    if not is_desk_active(current):
        raise BotError(
            "the bot is not active -- press Activate on the Bots page",
            409,
            BOT_REASON_NOT_ACTIVE,
        )
    require_places_allowed()          # the desk padlock (BOT_TRADING_LOCKED)
    assert_fresh_heartbeat(current)
    return current
