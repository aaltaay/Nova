"""Every gate between the bot and a fire, in one list (ADR 027).

``gates(row)`` is what the Bots page draws; the fire path checks the same
facts (``autonomy.assert_can_fire``, ``eligibility.assert_symbol_can_fire``,
``entry_rules``, ``execution.service``). Each gate is ``{id, ok, stage,
detail}``: ``stage`` is ``activate`` for a gate Activate at Strategy needs, or
``fire`` for one each order meets on its own. Owner: this module (no state).

ADR 030: the read-out gates Live only. On Paper and Sim (fake money) Strategy
skips it -- ``readout_required`` is the one rule, and a venue that cannot be
read counts as Live.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from bot.errors import BotError
from constants_bot import BOT_LEVEL_STRATEGY, BOT_REASON_READOUT_NOT_PASSED

logger = logging.getLogger(__name__)
_readout_for_tests: dict[str, Any] | None = None


def chosen_setup() -> str:
    """The setup that plays (ADR 027); the default when the session cannot be read."""
    from constants_bot import BOT_SETUP_DEFAULT

    try:
        from bot.persist import load_session

        return str(load_session().get("setup") or BOT_SETUP_DEFAULT)
    except Exception:
        logger.warning("bot gates: the chosen setup is unreadable -- reading the default's read-out", exc_info=True)
        return BOT_SETUP_DEFAULT


def readout() -> dict[str, Any]:
    """The chosen setup's read-out (``setup_scanner.readout``, per setup since ADR 031)."""
    if _readout_for_tests is not None:
        return _readout_for_tests
    from setup_scanner.readout import current

    return current(setup=chosen_setup())


def readout_passed() -> bool:
    return bool(readout().get("passed"))


def current_venue() -> str | None:
    """The desk venue (``live`` | ``paper`` | ``sim``); None when it cannot be read."""
    try:
        from sim.mode import venue

        return venue()
    except Exception:
        logger.warning("bot gates: the desk venue is unreadable -- the read-out applies as on Live",
                       exc_info=True)
        return None


def readout_required(venue: str | None = None) -> bool:
    """Live waits on the read-out; Paper and Sim do not (ADR 030). Unknown counts as Live."""
    from constants_sim import DESK_PRACTICE_VENUES

    current = venue if venue is not None else current_venue()
    return current not in DESK_PRACTICE_VENUES


def readout_open(venue: str | None = None) -> bool:
    """Strategy may be active and fire: the read-out passed, or this venue does not need it."""
    return not readout_required(venue) or readout_passed()


def assert_readout_open() -> None:
    if readout_open():
        return
    out = readout()
    label = chosen_setup().replace("_", "-")
    raise BotError(
        f"Strategy waits on the {label} read-out -- {out.get('reason') or out.get('state')}",
        409,
        BOT_REASON_READOUT_NOT_PASSED,
    )


def assert_can_activate(row: dict[str, Any]) -> None:
    """Activate at Strategy waits on the read-out on Live; at Off / Eyes nothing can fire (ADR 027, 030)."""
    if int(row.get("level") or 0) >= BOT_LEVEL_STRATEGY:
        assert_readout_open()


def _safe(fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _gate(gid: str, ok: bool, stage: str, **detail: Any) -> dict[str, Any]:
    return {"id": gid, "ok": bool(ok), "stage": stage, "detail": detail}


def gates(row: dict[str, Any]) -> list[dict[str, Any]]:
    from bot import entry_rules
    from bot.clock import lock_is_active
    from bot.day_pnl import commission_hold
    from bot.eligibility import holds_depth_line, normalize_symbols
    from ibkr.trading_allowed import places_allowed
    import kill_switch

    level = int(row.get("level") or 0)
    symbols = normalize_symbols(row.get("symbol_allowlist"))
    held = [s for s in symbols if _safe(lambda s=s: holds_depth_line(s), False)]
    places_ok, places_reason = _safe(places_allowed, (False, "trading gate unreadable"))
    out = readout()
    venue = current_venue()
    waived = not readout_required(venue)
    window = _safe(entry_rules.status, None)
    held_for_commissions = commission_hold(venue)     # #564: Live only; never raises
    return [
        _gate("level", level >= BOT_LEVEL_STRATEGY, "activate", level=level),
        _gate("allowlist", bool(symbols), "activate", count=len(symbols)),
        _gate("desk_armed", places_ok, "activate", reason=None if places_ok else places_reason or None),
        _gate("depth_lines", bool(symbols) and len(held) == len(symbols), "fire",
              held=held, missing=[s for s in symbols if s not in held]),
        _gate("readout", bool(out.get("passed")) or waived, "activate", state=out.get("state"),
              go_triggered=(out.get("go") or {}).get("triggered"), min_go=(out.get("rules") or {}).get("min_go"),
              waived=waived and not out.get("passed"), venue=venue),
        _gate("bot_trip", not row.get("soft_breaker_fired"), "activate"),
        _gate("day_lock", not lock_is_active(row.get("hard_lock_until_date")), "fire",
              until=row.get("hard_lock_until_date")),
        _gate("kill_switch", not _safe(kill_switch.is_tripped, True), "fire"),
        _gate("window", bool(window and window["open"] and window["entries_today"] < window["max_entries"]),
              "fire", **(window or {})),
        _gate("commissions", held_for_commissions is None, "fire", **(held_for_commissions or {})),
    ]


def set_readout_for_tests(value: dict[str, Any] | None) -> None:
    global _readout_for_tests
    _readout_for_tests = value


def passed_readout_for_tests() -> dict[str, Any]:
    return {"state": "passed", "passed": True, "reason": "test", "go": {"triggered": 50},
            "control": {"triggered": 0}, "rules": {"min_go": 50}}
