"""Every gate between the bot and a fire, in one list (ADR 027).

``gates(row)`` is what the Bots page draws; the fire path checks the same
facts (``autonomy.assert_can_fire``, ``eligibility.assert_symbol_can_fire``,
``entry_rules``, ``execution.service``). Each gate is ``{id, ok, stage,
detail}``: ``stage`` is ``activate`` for a gate Activate at Strategy needs, or
``fire`` for one each order meets on its own. Owner: this module (no state).
"""
from __future__ import annotations

from typing import Any, Callable

from bot.errors import BotError
from constants_bot import BOT_LEVEL_STRATEGY, BOT_REASON_READOUT_NOT_PASSED

_readout_for_tests: dict[str, Any] | None = None


def readout() -> dict[str, Any]:
    """The chosen setup's read-out (first pullback: ``setup_scanner.readout``)."""
    if _readout_for_tests is not None:
        return _readout_for_tests
    from setup_scanner.readout import current

    return current()


def readout_passed() -> bool:
    return bool(readout().get("passed"))


def assert_readout_passed() -> None:
    out = readout()
    if not out.get("passed"):
        raise BotError(
            f"Strategy waits on the first-pullback read-out -- {out.get('reason') or out.get('state')}",
            409,
            BOT_REASON_READOUT_NOT_PASSED,
        )


def assert_can_activate(row: dict[str, Any]) -> None:
    """Activate at Strategy waits on the read-out; at Off / Eyes nothing can fire (ADR 027)."""
    if int(row.get("level") or 0) >= BOT_LEVEL_STRATEGY:
        assert_readout_passed()


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
    from bot.eligibility import holds_depth_line, normalize_symbols
    from ibkr.trading_allowed import places_allowed
    import kill_switch

    level = int(row.get("level") or 0)
    symbols = normalize_symbols(row.get("symbol_allowlist"))
    held = [s for s in symbols if _safe(lambda s=s: holds_depth_line(s), False)]
    places_ok, places_reason = _safe(places_allowed, (False, "trading gate unreadable"))
    out = readout()
    window = _safe(entry_rules.status, None)
    return [
        _gate("level", level >= BOT_LEVEL_STRATEGY, "activate", level=level),
        _gate("allowlist", bool(symbols), "activate", count=len(symbols)),
        _gate("desk_armed", places_ok, "activate", reason=None if places_ok else places_reason or None),
        _gate("depth_lines", bool(symbols) and len(held) == len(symbols), "fire",
              held=held, missing=[s for s in symbols if s not in held]),
        _gate("readout", bool(out.get("passed")), "activate", state=out.get("state"),
              go_triggered=(out.get("go") or {}).get("triggered"), min_go=(out.get("rules") or {}).get("min_go")),
        _gate("bot_trip", not row.get("soft_breaker_fired"), "activate"),
        _gate("day_lock", not lock_is_active(row.get("hard_lock_until_date")), "fire",
              until=row.get("hard_lock_until_date")),
        _gate("kill_switch", not _safe(kill_switch.is_tripped, True), "fire"),
        _gate("window", bool(window and window["open"] and window["entries_today"] < window["max_entries"]),
              "fire", **(window or {})),
    ]


def set_readout_for_tests(value: dict[str, Any] | None) -> None:
    global _readout_for_tests
    _readout_for_tests = value


def passed_readout_for_tests() -> dict[str, Any]:
    return {"state": "passed", "passed": True, "reason": "test", "go": {"triggered": 50},
            "control": {"triggered": 0}, "rules": {"min_go": 50}}
