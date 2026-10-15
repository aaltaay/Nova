"""The ABCD's parameter table (operator ask 2026-10-15). Pure data.

The pattern's numbers are its own (``setup_scanner/abcd_shape.py``): how far a swing moves to count, how far B may
double-top the high, how far C may sit under A, how much of the drop B takes back, and the minutes from A to the
break of B. Each tolerance is a percentage or a cent, whichever is more, the way the flat top's touch reads. The EMA
and the MACD, the entry offset, the near band, the risk caps and the target menu are every setup's, with the ABCD's
defaults where the material reads it differently: a wider stop cap (the stop sits under C), arming until 15:30, and
target 1 at the high of day. The stock filter, the tape gate, the flow and the grade are every setup's.

Watch only (``constants_bot.BOT_WATCH_ONLY_SETUPS``): no bot group -- nothing here ever buys. ``catalogue.py`` merges
this table with the others.
"""
from __future__ import annotations

import dataclasses

from constants_bot import BOT_SETUP_ABCD
from constants_setups import (
    SETUPS_ABCD_B_OVER_PCT,
    SETUPS_ABCD_BOUNCE,
    SETUPS_ABCD_C_UNDER_PCT,
    SETUPS_ABCD_ENTRY_CUTOFF_ET,
    SETUPS_ABCD_MAX_MINUTES,
    SETUPS_ABCD_MAX_PER_SYMBOL_DAY,
    SETUPS_ABCD_STOP_CAP_DOLLARS,
    SETUPS_ABCD_STOP_OFFSET_DOLLARS,
    SETUPS_ABCD_SWING_PCT,
    SETUPS_ABCD_TOL_DOLLARS,
    SETUPS_ENTRY_OFFSET_DOLLARS,
    SETUPS_TARGET_HOD,
)
from setup_templates.params import _BAILOUT, _FLOW, _GRADE, _STOCK, _TAPE, _ema, _macd, _near, _risk, _window
from setup_templates.params_targets import TARGETS
from setup_templates.spec import INT, NUMBER, ParamSpec, _p, _pct

_PATTERN: tuple[ParamSpec, ...] = (
    _p("abcd_swing_pct", "setup", "A swing moves at least", NUMBER, _pct(SETUPS_ABCD_SWING_PCT), unit="%", min=0.5,
       max=20, step=0.5,
       help="The high to A, A to B and B to C each move at least this far; a smaller wiggle is inside one swing. "
            "Smaller finds more ABCDs, and more of them noise."),
    _p("abcd_b_over_pct", "setup", "B may double-top the high by", NUMBER, _pct(SETUPS_ABCD_B_OVER_PCT),
       unit="% over it", min=0, max=5, step=0.1,
       help="B fails to clear the high: it stays under it, or over it by at most this (or the cent below, whichever "
            "is more) -- a double top. A push past it is a new high, and the ABCD starts again from there."),
    _p("abcd_c_under_pct", "setup", "C may sit under A by", NUMBER, _pct(SETUPS_ABCD_C_UNDER_PCT), unit="% under it",
       min=0, max=5, step=0.1,
       help="C is a higher low: every low after A stays over it, or under it by at most this (or the cent below). "
            "A lower low is stair-stepping down: the ABCD fails until a new high."),
    _p("abcd_tol_dollars", "setup", "... or within", NUMBER, SETUPS_ABCD_TOL_DOLLARS, unit="$", min=0, max=1,
       step=0.01, help="Both tolerances above are at least this many dollars: a cent is one tick."),
    _p("abcd_bounce_pct", "setup", "B takes back at least", NUMBER, _pct(SETUPS_ABCD_BOUNCE),
       unit="% of the drop to A", min=10, max=100, step=5,
       help="From A, B climbs back at least this share of the way to the high: a real push, not a bounce."),
    _p("abcd_max_minutes", "setup", "A to the break of B within", INT, SETUPS_ABCD_MAX_MINUTES, unit="minutes",
       min=3, max=120, step=1,
       help="The material's 1-minute ABCD forms over 15, sometimes 20 minutes; consolidating longer is weak. Past "
            "this the ABCD fails until a new high."),
) + _ema("The scoring exit's EMA (the ABCD reads no EMA to arm).") + _macd(
    "The newest candle's MACD histogram is above zero when it arms (the material: a negative MACD works against it).") + (
    _p("max_per_symbol_day", "setup", "ABCDs a symbol a day", INT, SETUPS_ABCD_MAX_PER_SYMBOL_DAY, unit="setups", min=1,
       max=10, step=1, help="The first ABCD, then the second -- no more on one symbol that day. The next needs a new "
                            "high."),
)


def _with(specs: tuple[ParamSpec, ...], **defaults: object) -> tuple[ParamSpec, ...]:
    """``specs`` with the ABCD's own defaults where it reads a shared parameter differently."""
    return tuple(dataclasses.replace(s, default=defaults[s.key]) if s.key in defaults else s for s in specs)


_ENTRY: tuple[ParamSpec, ...] = (
    _p("entry_offset", "entry", "Buy over B by", NUMBER, SETUPS_ENTRY_OFFSET_DOLLARS, unit="$", min=0, max=1, step=0.01,
       help="The entry is B's high plus this: bought on the break of B (point D), the material's proper entry."),
) + _with(_window("Arms from", "No ABCD arms before this time.",
                  "No ABCD arms, and none triggers, at or after this time."),
          entry_cutoff=SETUPS_ABCD_ENTRY_CUTOFF_ET) + _near()

_RISK: tuple[ParamSpec, ...] = _with(_risk("Entry minus the stop under C. A bigger risk skips the ABCD."),
                                     stop_cap=SETUPS_ABCD_STOP_CAP_DOLLARS) + (
    _p("abcd_stop_offset", "risk", "Stop under C by", NUMBER, SETUPS_ABCD_STOP_OFFSET_DOLLARS, unit="$", min=0, max=1,
       step=0.01, help="The stop sits this far under C, the lowest low since B."),
)

ABCD_CATALOGUE: dict[str, tuple[ParamSpec, ...]] = {
    BOT_SETUP_ABCD: _STOCK + _PATTERN + _ENTRY + _RISK + (*_with(TARGETS, target1_kind=SETUPS_TARGET_HOD), _BAILOUT)
    + _TAPE + _FLOW + _GRADE,
}

ABCD_SOURCES: dict[str, str] = {
    BOT_SETUP_ABCD: ("Watch only: never tested -- the eyes watch, score and draw it, and Nova never trades it. Your "
                     "material's ABCD: a squeeze to the high, a pullback (A), a push that fails to clear the high "
                     "(B), a higher low (C), bought on the break of B (D), target 1 the high of day. The tolerances are "
                     "chosen, the way the flat top's touch is. It arms 07:00-15:30. Every template is watched at once."),
}
