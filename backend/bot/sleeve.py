"""The sleeve: one per venue, for every Nova automatic buy (ADR 042 E).

The session's ``caps`` are the desk venue's own sleeve -- the venue's dial carries them
(``bot.venue_levels``), so Paper, Sim and Live each keep theirs. A sleeve is:

- ``risk_usd``: the risk per trade a Nova automatic buy (the bot, Auto-entry) is sized by;
- ``max_shares`` / ``bp_budget_usd``: the most it may hold (``bot.sizing``);
- ``working_ttl_sec``: how long any Nova entry may rest unfilled (the bot, Auto-entry, Approve);
- ``extended_hours``: whether the bot and Auto-entry may buy outside 09:30-16:00 ET;
- ``entries_per_day``: Nova's automatic entries per venue day, the bot and Auto-entry together;
- ``api_kinds``: the order kinds the localhost bot API may send (``allowlist`` until ADR 042).

A value outside its bounds is refused with them (``BOT_CAPS_INVALID``), never clamped in
silence. Owner: this module (the rules; the session file is ``bot.persist``'s).
"""
from __future__ import annotations

import math
from typing import Any

from bot.errors import BotError
from bot.kinds import default_allowlist
from constants_bot import (
    BOT_BP_BUDGET_HARD_MAX_USD,
    BOT_BP_BUDGET_MIN_USD,
    BOT_BREAKER_VENUES,
    BOT_DEFAULT_BP_BUDGET_USD,
    BOT_DEFAULT_MAX_SHARES,
    BOT_DEFAULT_RISK_USD,
    BOT_DEFAULT_WORKING_TTL_SEC,
    BOT_ENTRIES_PER_DAY,
    BOT_ENTRIES_PER_DAY_MAX,
    BOT_ENTRIES_PER_DAY_MIN,
    BOT_MAX_SHARES_CAP,
    BOT_MAX_SHARES_MIN,
    BOT_REASON_CAPS_INVALID,
    BOT_RISK_MAX_USD,
    BOT_RISK_MIN_USD,
    BOT_WORKING_TTL_MAX_SEC,
    BOT_WORKING_TTL_MIN_SEC,
)

# ``[least, most]`` for each number (the wire's ``caps_bounds``).
BOUNDS: dict[str, tuple[float, float]] = {
    "risk_usd": (BOT_RISK_MIN_USD, BOT_RISK_MAX_USD),
    "max_shares": (BOT_MAX_SHARES_MIN, BOT_MAX_SHARES_CAP),
    "bp_budget_usd": (BOT_BP_BUDGET_MIN_USD, BOT_BP_BUDGET_HARD_MAX_USD),
    "working_ttl_sec": (BOT_WORKING_TTL_MIN_SEC, BOT_WORKING_TTL_MAX_SEC),
    "entries_per_day": (BOT_ENTRIES_PER_DAY_MIN, BOT_ENTRIES_PER_DAY_MAX),
}
_INTS = frozenset({"max_shares", "working_ttl_sec", "entries_per_day"})
_LABELS = {"risk_usd": "risk per trade", "max_shares": "max shares", "bp_budget_usd": "buying-power budget",
           "working_ttl_sec": "entry time to live", "entries_per_day": "entries a day"}


def defaults() -> dict[str, Any]:
    return {"risk_usd": BOT_DEFAULT_RISK_USD, "max_shares": BOT_DEFAULT_MAX_SHARES,
            "bp_budget_usd": BOT_DEFAULT_BP_BUDGET_USD, "working_ttl_sec": BOT_DEFAULT_WORKING_TTL_SEC,
            "extended_hours": True, "entries_per_day": BOT_ENTRIES_PER_DAY, "api_kinds": default_allowlist()}


def bounds() -> dict[str, list[float]]:
    return {k: [lo, hi] for k, (lo, hi) in BOUNDS.items()}


def _within(key: str, value: float) -> float:
    lo, hi = BOUNDS[key]
    return max(lo, min(hi, value))


def _kinds(raw: Any) -> list[str]:
    allowed = default_allowlist()
    if not isinstance(raw, (list, tuple)):
        return list(allowed)
    return [k for k in raw if k in allowed]


def normalize(raw: Any) -> dict[str, Any]:
    """A stored sleeve read back: every field present and inside its bounds (a stored value
    out of bounds -- a hand-edited file, an older build -- is brought inside them)."""
    raw = raw if isinstance(raw, dict) else {}
    out = defaults()
    for key in BOUNDS:
        try:
            value = float(raw.get(key))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        value = _within(key, value)
        out[key] = int(value) if key in _INTS else value
    # On unless the operator turned it off: the default bot windows open at 07:00 ET (ADR 042 E).
    if "extended_hours" in raw:
        out["extended_hours"] = bool(raw.get("extended_hours"))
    kinds = raw.get("api_kinds", raw.get("allowlist"))
    if kinds is not None:
        out["api_kinds"] = _kinds(kinds)
    return out


def apply(current: Any, patch: dict[str, Any]) -> tuple[dict[str, Any], dict[str, tuple[Any, Any]]]:
    """``PATCH {caps: {...}}`` on one venue's sleeve: ``(sleeve, {field: (before, after)})``.

    Refuses (400 ``BOT_CAPS_INVALID``) a number outside its bounds or an unknown order kind,
    and changes nothing then."""
    before = normalize(current)
    after = dict(before)
    for key, value in patch.items():
        if key == "venue":
            continue
        if key in BOUNDS:
            lo, hi = BOUNDS[key]
            try:
                num = float(value)
            except (TypeError, ValueError):
                raise BotError(f"{_LABELS[key]} is a number", 400, BOT_REASON_CAPS_INVALID) from None
            if not math.isfinite(num) or not lo <= num <= hi:
                raise BotError(f"{_LABELS[key]} is {lo:g} to {hi:g}, not {value!r}", 400, BOT_REASON_CAPS_INVALID)
            if key in _INTS and num != int(num):
                raise BotError(f"{_LABELS[key]} is a whole number", 400, BOT_REASON_CAPS_INVALID)
            after[key] = int(num) if key in _INTS else num
        elif key == "extended_hours":
            after[key] = bool(value)
        elif key in ("api_kinds", "allowlist"):
            if not isinstance(value, (list, tuple)):
                raise BotError("api_kinds is a list of order kinds", 400, BOT_REASON_CAPS_INVALID)
            unknown = [k for k in value if k not in default_allowlist()]
            if unknown:
                raise BotError(f"unknown order kinds for the localhost bot API: {', '.join(map(str, unknown))}",
                               400, BOT_REASON_CAPS_INVALID)
            after["api_kinds"] = list(value)
        else:
            raise BotError(f"the sleeve has no {key!r}", 400, BOT_REASON_CAPS_INVALID)
    changed = {k: (before[k], after[k]) for k in after if after[k] != before[k]}
    return after, changed


def view(caps: Any, venue: str | None) -> dict[str, Any]:
    """The wire's ``caps``: the sleeve, its venue, and ``allowlist`` as a legacy alias of ``api_kinds``."""
    out = normalize(caps)
    return {"venue": venue, **out, "allowlist": list(out["api_kinds"])}


def of(row: dict[str, Any]) -> dict[str, Any]:
    """The desk venue's sleeve from the session row (normalized)."""
    return normalize(row.get("caps"))


def by_venue(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """``{VENUE: caps}`` -- the desk's own and every other venue's stored sleeve."""
    from bot.venue_levels import dial_of

    return {v: view(dial_of(row, v).get("caps"), v) for v in BOT_BREAKER_VENUES}
