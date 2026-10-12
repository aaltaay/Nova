"""The pullback dip's parameter table (#847; operator ask 2026-10-12). Pure data.

The run and the pullback are the first pullback's own parameters (``params.py``: the leg, the new high, the high of
day, the pullback's length, what it gives back, the EMA and the MACD), with the dip's words where it reads them
differently -- the pullback counts its entry candle. The entry is the dip's own: a bottoming wick or the first green
close (``setup_scanner/dip_candle.py``), bought a cent over that candle's close. The stop sits a cent under the
pullback's low, inside the first pullback's caps. The targets are the menu's with the first half at the high the
pullback came off. The stock filter, the tape gate, the flow and the grade are every setup's.

Watch only (``constants_bot.BOT_WATCH_ONLY_SETUPS``): no bot group -- nothing here ever buys -- no near band and no
slippage counted in the risk (nothing triggers on a live price; the entry's cent over the close stands for the
slippage, as a flat-top hold's does). ``catalogue.py`` merges this table with the others.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from constants_bot import BOT_SETUP_PULLBACK_DIP
from constants_setups import (
    SETUPS_DIP_CLOSE_MIN,
    SETUPS_DIP_ENTRY,
    SETUPS_DIP_ENTRY_GREEN,
    SETUPS_DIP_ENTRY_WICK,
    SETUPS_DIP_MAX_PULLBACK_BARS,
    SETUPS_DIP_MIN_PULLBACK_BARS,
    SETUPS_DIP_MIN_RED_BARS,
    SETUPS_DIP_STOP_OFFSET_DOLLARS,
    SETUPS_DIP_WICK_MIN,
    SETUPS_DIP_WICK_MIN_DOLLARS,
    SETUPS_TARGET_PULLBACK_HIGH,
)
from setup_templates.params import _BAILOUT, _FIRST_PULLBACK, _FLOW, _GRADE, _STOCK, _TAPE, _window
from setup_templates.params_targets import TARGETS
from setup_templates.spec import CHOICE, INT, NUMBER, ParamSpec, _p, _pct

_FP = {s.key: s for s in _FIRST_PULLBACK}


def _fp(key: str, **changes: Any) -> ParamSpec:
    """The first pullback's own parameter, with the dip's words or default where it reads it differently."""
    return dataclasses.replace(_FP[key], **changes)


_RUN: tuple[ParamSpec, ...] = (
    _fp("leg_pct"), _fp("leg_window"), _fp("leg_lookback"), _fp("require_hod"),
    _fp("min_pullback_bars", default=SETUPS_DIP_MIN_PULLBACK_BARS, unit="candles",
        help="Fewest candles after the leg high, the entry candle included: two is one candle down, then the one "
             "that bottoms it."),
    _fp("max_pullback_bars", default=SETUPS_DIP_MAX_PULLBACK_BARS, unit="candles",
        help="Most candles after the leg high, the entry candle included, before the pullback ran too long: the "
             "first pullback's three, then the one that bottoms it."),
    _fp("max_retrace", help="The pullback's low -- the entry candle's wick included -- gives back less than this "
                            "share of the leg."),
    _fp("ema_period", help="Every pullback candle, the entry candle included, closes at or above this EMA."),
    _fp("ema_tol"),
    _fp("macd_positive", help="The entry candle's MACD histogram is above zero (the front side of the move)."),
    _fp("macd_fast"), _fp("macd_slow"), _fp("macd_signal"),
    _fp("max_per_symbol_day", help="The first dip, then the second -- no more on one symbol that day. The next needs "
                                   "a new leg."),
)

_ENTRY: tuple[ParamSpec, ...] = (
    _p("dip_entry", "entry", "Entry", CHOICE, SETUPS_DIP_ENTRY,
       choices=((SETUPS_DIP_ENTRY_WICK, "the bottoming wick: buying the dip"),
                (SETUPS_DIP_ENTRY_GREEN, "the first candle to close green")),
       help="Wick: the candle that makes the pullback's low with a long lower wick and closes high in its range. "
            "Green: the first pullback candle that closes over its open after a red one. Either is bought at its "
            "close. Every template is watched at once: make one of each to score both."),
    _p("dip_wick_min_pct", "entry", "Lower wick at least", NUMBER, _pct(SETUPS_DIP_WICK_MIN), unit="% of the candle",
       min=10, max=95, step=5, help="Wick entry: from the lower of the open and close down to the low, as a share of "
                                   "the candle's range."),
    _p("dip_wick_min_dollars", "entry", "... and at least", NUMBER, SETUPS_DIP_WICK_MIN_DOLLARS, unit="$", min=0,
       max=1, step=0.01, help="Wick entry: a lower wick of a cent is the spread, not buyers."),
    _p("dip_close_min_pct", "entry", "Closes up its range at least", NUMBER, _pct(SETUPS_DIP_CLOSE_MIN),
       unit="% from the low", min=0, max=100, step=5,
       help="Wick entry: the close sits this far up from the candle's low to its high -- the dip was bought."),
    _p("dip_min_red_bars", "entry", "Green after at least", INT, SETUPS_DIP_MIN_RED_BARS, unit="red candles", min=1,
       max=10, step=1, help="Green entry: the first green close counts after this many red pullback candles. A "
                            "later green is not the first."),
    _fp("entry_offset", label="Buy over the entry candle's close by",
        help="The entry is the entry candle's close plus this: a limit just over the close, never the ask chased."),
) + _window("Arms from", "No dip is bought before this time.",
            "No dip is bought at or after this time (its candle's close).")

_RISK: tuple[ParamSpec, ...] = (
    _fp("stop_cap", help="Entry minus the stop. A bigger risk skips the dip."),
    _fp("min_stop"),
    _p("dip_stop_offset", "risk", "Stop under the pullback's low by", NUMBER, SETUPS_DIP_STOP_OFFSET_DOLLARS, unit="$",
       min=0, max=1, step=0.01, help="The stop sits this far under the pullback's low, the entry candle's wick "
                                     "included."),
)


def _targets() -> tuple[ParamSpec, ...]:
    """The menu, the first half at the high the pullback came off -- the material's first target for a dip."""
    return tuple(dataclasses.replace(s, default=SETUPS_TARGET_PULLBACK_HIGH) if s.key == "target1_kind" else s
                 for s in TARGETS)


DIP_CATALOGUE: dict[str, tuple[ParamSpec, ...]] = {
    BOT_SETUP_PULLBACK_DIP: _STOCK + _RUN + _ENTRY + _RISK + (*_targets(), _BAILOUT) + _TAPE + _FLOW + _GRADE,
}

DIP_SOURCES: dict[str, str] = {
    BOT_SETUP_PULLBACK_DIP: ("Watch only (#847): the eyes watch, score and draw it, and Nova never trades it. The "
                             "first pullback's run and pullback, bought at the candle that bottoms it -- the bottoming "
                             "wick or the first green close, your material's pullback-bottom entries -- with the high "
                             "of the pullback as target 1. It arms 07:00-11:30. Every template is watched at once."),
}
