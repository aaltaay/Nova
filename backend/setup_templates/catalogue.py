"""Every number a setup runs on (ADR 029): the parameter catalogue.

maintainer: one-concern the parameter table of every setup the playbook lists, and the one validator for it

Pure data and validation: no I/O, no scanner imports. One entry per setup the
playbook lists (``constants_bot.BOT_SETUPS``) -- its parameters in the order the
Bots page draws them, grouped, each with a unit, bounds, and the default that
is the setup's pre-registered rule. ``live`` says whether a running scanner
reads the parameter; a setup without a scanner keeps its research parameters
(``research/momentum/backtest_setups.py``, ``research/orb/backtest_gng.py``)
for when it gets one.

Values are kept in the unit the operator types -- percent as 5, not 0.05; a
float in millions of shares -- and ``setup_scanner/lane_params.py`` converts
them for the scanner in one place. A nullable parameter is off when ``None``.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any

from constants_bot import (
    BOT_ENTRIES_PER_DAY,
    BOT_ENTRY_WINDOW_END_ET,
    BOT_ENTRY_WINDOW_START_ET,
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SETUP_FLAT_TOP,
    BOT_SETUP_GAP_AND_GO,
    BOT_SETUP_MICRO_PULLBACK,
    BOT_SETUP_RED_TO_GREEN,
    BOT_SETUPS,
    BOT_SETUPS_WITH_SCANNER,
)
from constants_setups import (
    SETUPS_BAILOUT_BARS,
    SETUPS_EMA_PERIOD,
    SETUPS_EMA_TOLERANCE,
    SETUPS_ENTRY_CUTOFF_ET,
    SETUPS_ENTRY_OFFSET_DOLLARS,
    SETUPS_LEG_LOOKBACK_BARS,
    SETUPS_LEG_PCT,
    SETUPS_LEG_WINDOW_BARS,
    SETUPS_MACD_FAST,
    SETUPS_MACD_POSITIVE,
    SETUPS_MACD_SIGNAL,
    SETUPS_MACD_SLOW,
    SETUPS_MAX_PER_SYMBOL_DAY,
    SETUPS_MAX_PULLBACK_BARS,
    SETUPS_MAX_RETRACE,
    SETUPS_MIN_PULLBACK_BARS,
    SETUPS_MIN_STOP_DOLLARS,
    SETUPS_NEAR_DOLLARS,
    SETUPS_NEAR_PCT,
    SETUPS_PILLAR_MAX_FLOAT,
    SETUPS_PILLAR_MAX_PRICE,
    SETUPS_PILLAR_MIN_CHANGE_PCT,
    SETUPS_PILLAR_MIN_PRICE,
    SETUPS_PILLAR_MIN_RVOL,
    SETUPS_REQUIRE_HOD,
    SETUPS_RISK_SLIPPAGE_DOLLARS,
    SETUPS_SESSION_START_ET,
    SETUPS_STOP_CAP_DOLLARS,
    SETUPS_TARGET_FIXED_DOLLARS,
    SETUPS_TARGET_MODE,
    SETUPS_TARGET_R,
    TAPE_GATE_BAND_DOLLARS,
    TAPE_GATE_BIG_SELLER_SHARES,
    TAPE_GATE_HIDDEN_SELLER_MULT,
    TAPE_GATE_MIN_ASK_PRINTS,
    TAPE_GATE_RED_BURST_MULT,
    TAPE_GATE_SPREAD_MAX_DOLLARS,
    TAPE_GATE_SPREAD_MAX_PCT,
    TAPE_GATE_STALE_BOOK_SEC,
    TAPE_GATE_THIN_FRACTION,
    TAPE_GATE_WALL_SHARES,
    TAPE_GATE_WINDOW_SEC,
)

NUMBER, INT, BOOL, TIME, CHOICE = "number", "int", "bool", "time", "choice"
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_DECIMALS = 6


class TemplateError(ValueError):
    """A value the catalogue refuses; ``field`` names the parameter (or None)."""

    def __init__(self, message: str, field: str | None = None, code: str = "TEMPLATE_INVALID"):
        super().__init__(message)
        self.field = field
        self.code = code


@dataclass(frozen=True)
class ParamSpec:
    key: str
    group: str
    label: str
    kind: str
    default: Any
    unit: str = ""
    min: float | str | None = None
    max: float | str | None = None
    step: float | None = None
    choices: tuple[tuple[str, str], ...] = ()
    nullable: bool = False
    help: str = ""
    live: bool = True

    def wire(self) -> dict[str, Any]:
        return {
            "key": self.key, "group": self.group, "label": self.label, "kind": self.kind,
            "default": self.default, "unit": self.unit, "min": self.min, "max": self.max,
            "step": self.step, "choices": [{"value": v, "label": lbl} for v, lbl in self.choices],
            "nullable": self.nullable, "help": self.help, "live": self.live,
        }


GROUP_LABELS: dict[str, tuple[str, str]] = {
    "stock": ("Stock filter", "Checked when a setup arms, from the Five Pillars read then. Off lets every name the scanner follows through."),
    "universe": ("Universe", "The symbol-days the research tested."),
    "setup": ("The pattern", "What the bars must show before a setup arms."),
    "entry": ("Entry", "Where the buy goes and when."),
    "risk": ("Risk and target", "The stop, the risk it allows, the target, and the scoring exit."),
    "tape": ("Tape gate", "Read from the Level 2 and time and sales when price is near the trigger."),
    "grade": ("Five Pillars grade", "Grades every armed setup A / B / C. A pillar Nova does not know never passes."),
    "bot": ("Bot entries at Strategy", "The bot's own rules while this template is in play."),
}


def _pct(fraction: float) -> float:
    return round(fraction * 100, _DECIMALS)


def _p(key: str, group: str, label: str, kind: str, default: Any, **kw: Any) -> ParamSpec:
    return ParamSpec(key=key, group=group, label=label, kind=kind, default=default, **kw)


# -- First pullback: the live scanner's numbers (constants_setups, ADR 022). --------
_FIRST_PULLBACK: tuple[ParamSpec, ...] = (
    _p("min_price", "stock", "Price at least", NUMBER, None, unit="$", min=0.1, max=1000, step=0.01, nullable=True,
       help="Arm only when the last price is at least this."),
    _p("max_price", "stock", "Price at most", NUMBER, None, unit="$", min=0.1, max=1000, step=0.01, nullable=True,
       help="Arm only when the last price is at most this."),
    _p("max_float_m", "stock", "Float at most", NUMBER, None, unit="M shares", min=0.1, max=10000, step=0.1,
       nullable=True, help="Arm only when the float is at most this many million shares."),
    _p("min_change_pct", "stock", "Up on the day at least", NUMBER, None, unit="%", min=0, max=10000, step=1,
       nullable=True, help="Arm only when the stock is up at least this much from the prior close."),
    _p("min_rvol", "stock", "Relative volume at least", NUMBER, None, unit="x", min=0, max=10000, step=0.5,
       nullable=True, help="Arm only when relative volume is at least this."),
    _p("require_catalyst", "stock", "Needs a catalyst", BOOL, False,
       help="Arm only when the News pillar passes: a real company catalyst since the prior close."),
    _p("min_grade", "stock", "Grade at least", CHOICE, "C", choices=(("A", "A"), ("B", "B or better"), ("C", "any")),
       help="Arm only setups graded this well or better."),
    _p("unknown_passes", "stock", "A fact Nova does not know passes", BOOL, True,
       help="On: an unknown price, float, change or volume does not block the filter. Off: it does."),

    _p("leg_pct", "setup", "Leg at least", NUMBER, _pct(SETUPS_LEG_PCT), unit="%", min=1, max=100, step=0.5,
       help="The leg high is at least this far over the lowest low of the leg window."),
    _p("leg_window", "setup", "Leg window", INT, SETUPS_LEG_WINDOW_BARS, unit="bars", min=2, max=120, step=1,
       help="The bars ending at the leg high that the leg is measured over."),
    _p("leg_lookback", "setup", "New high over", INT, SETUPS_LEG_LOOKBACK_BARS, unit="bars", min=5, max=240, step=1,
       help="The leg high is the highest high of this many bars before it."),
    _p("require_hod", "setup", "Leg high is the high of day", BOOL, SETUPS_REQUIRE_HOD,
       help="The leg high is also the day's high so far, pre-market included."),
    _p("min_pullback_bars", "setup", "Pullback at least", INT, SETUPS_MIN_PULLBACK_BARS, unit="bars", min=1, max=10, step=1,
       help="Fewest candles after the leg high."),
    _p("max_pullback_bars", "setup", "Pullback at most", INT, SETUPS_MAX_PULLBACK_BARS, unit="bars", min=1, max=10, step=1,
       help="Most candles after the leg high before the pullback ran too long."),
    _p("max_retrace", "setup", "Gives back less than", NUMBER, _pct(SETUPS_MAX_RETRACE), unit="% of the leg", min=5,
       max=100, step=5, help="The pullback's low gives back less than this share of the leg."),
    _p("ema_period", "setup", "Holds the EMA", INT, SETUPS_EMA_PERIOD, unit="bars", min=2, max=100, step=1,
       help="Every pullback candle closes at or above this EMA."),
    _p("ema_tol", "setup", "EMA slack", NUMBER, _pct(SETUPS_EMA_TOLERANCE), unit="%", min=0, max=10, step=0.1,
       help="A pullback close may sit this far under the EMA."),
    _p("macd_positive", "setup", "MACD histogram above zero", BOOL, SETUPS_MACD_POSITIVE,
       help="The last pullback candle's MACD histogram is above zero (the front side of the move)."),
    _p("macd_fast", "setup", "MACD fast", INT, SETUPS_MACD_FAST, unit="bars", min=2, max=60, step=1),
    _p("macd_slow", "setup", "MACD slow", INT, SETUPS_MACD_SLOW, unit="bars", min=3, max=120, step=1),
    _p("macd_signal", "setup", "MACD signal", INT, SETUPS_MACD_SIGNAL, unit="bars", min=2, max=60, step=1),
    _p("max_per_symbol_day", "setup", "Setups a symbol a day", INT, SETUPS_MAX_PER_SYMBOL_DAY, unit="setups", min=1,
       max=10, step=1, help="The first pullback, then the second -- no more on one symbol that day."),

    _p("entry_offset", "entry", "Buy over the pullback high by", NUMBER, SETUPS_ENTRY_OFFSET_DOLLARS, unit="$", min=0,
       max=1, step=0.01, help="The entry is the last pullback candle's high plus this."),
    _p("session_start", "entry", "Arms from", TIME, SETUPS_SESSION_START_ET, unit="ET", min="04:00", max="20:00",
       help="No setup arms before this time."),
    _p("entry_cutoff", "entry", "Arms until", TIME, SETUPS_ENTRY_CUTOFF_ET, unit="ET", min="04:00", max="20:00",
       help="No setup arms, and none triggers, at or after this time."),
    _p("near_dollars", "entry", "Near the trigger within", NUMBER, SETUPS_NEAR_DOLLARS, unit="$", min=0, max=2,
       step=0.01, help="Price this close to the trigger is when the tape is read (or the percent below, whichever is wider)."),
    _p("near_pct", "entry", "... or within", NUMBER, _pct(SETUPS_NEAR_PCT), unit="%", min=0, max=10, step=0.05),

    _p("stop_cap", "risk", "Largest risk a share", NUMBER, SETUPS_STOP_CAP_DOLLARS, unit="$", min=0.01, max=10,
       step=0.01, help="Entry minus the pullback low. A bigger risk skips the setup."),
    _p("min_stop", "risk", "Smallest risk a share", NUMBER, SETUPS_MIN_STOP_DOLLARS, unit="$", min=0, max=5, step=0.01,
       help="A smaller risk skips the setup: the stop would sit in the spread."),
    _p("risk_slippage", "risk", "Slippage counted in the risk", NUMBER, SETUPS_RISK_SLIPPAGE_DOLLARS, unit="$", min=0,
       max=1, step=0.01, help="Added to the risk before the two checks above, as the research did."),
    _p("target_mode", "risk", "Target 1", CHOICE, SETUPS_TARGET_MODE,
       choices=(("leg_or_r", "the leg high or R x risk, whichever is higher"), ("fixed", "a fixed amount over the entry")),
       help="Half comes off at target 1 and the stop moves to the entry (the scoring exit)."),
    _p("target_r", "risk", "R multiple", NUMBER, SETUPS_TARGET_R, unit="R", min=0.25, max=20, step=0.25,
       help="Used when target 1 is the leg high or R x risk."),
    _p("target_fixed", "risk", "Fixed target", NUMBER, SETUPS_TARGET_FIXED_DOLLARS, unit="$", min=0.01, max=10, step=0.01,
       help="Used when target 1 is a fixed amount over the entry."),
    _p("bailout_bars", "risk", "Out after", INT, SETUPS_BAILOUT_BARS, unit="bars", min=1, max=120, step=1,
       help="Scoring exit: this many candles without a close over the entry -> out at the close."),

    _p("tape_window_sec", "tape", "Looks back", NUMBER, TAPE_GATE_WINDOW_SEC, unit="s", min=1, max=120, step=1,
       help="The book samples and prints the gate reads."),
    _p("tape_stale_book_sec", "tape", "Book is stale after", NUMBER, TAPE_GATE_STALE_BOOK_SEC, unit="s", min=0.5,
       max=60, step=0.5, help="No book newer than this reads blind."),
    _p("spread_max", "tape", "Widest spread", NUMBER, TAPE_GATE_SPREAD_MAX_DOLLARS, unit="$", min=0.01, max=2,
       step=0.01, help="A wider spread vetoes (or the percent below, whichever is wider)."),
    _p("spread_max_pct", "tape", "... or", NUMBER, _pct(TAPE_GATE_SPREAD_MAX_PCT), unit="% of the ask", min=0.1, max=20,
       step=0.1),
    _p("band", "tape", "At the level up to", NUMBER, TAPE_GATE_BAND_DOLLARS, unit="$ over the trigger", min=0, max=1,
       step=0.01, help="Ask levels from 1 cent under the trigger to this far over it are at the level."),
    _p("big_seller", "tape", "Seller that vetoes", INT, int(TAPE_GATE_BIG_SELLER_SHARES), unit="shares", min=1000,
       max=10_000_000, step=1000, help="A displayed seller this big at the level vetoes."),
    _p("wall", "tape", "Seller that waits", INT, int(TAPE_GATE_WALL_SHARES), unit="shares", min=100,
       max=10_000_000, step=1000, help="A seller this big at the level waits until it thins."),
    _p("thin_fraction", "tape", "Thinning means down", NUMBER, _pct(TAPE_GATE_THIN_FRACTION), unit="%", min=5, max=95,
       step=5, help="The seller shrank by this much inside the window."),
    _p("min_ask_prints", "tape", "Green tape needs", INT, TAPE_GATE_MIN_ASK_PRINTS, unit="prints at the ask", min=1,
       max=200, step=1, help="And more volume at the ask than at the bid."),
    _p("hidden_mult", "tape", "Hidden seller at", NUMBER, TAPE_GATE_HIDDEN_SELLER_MULT, unit="x the inside ask", min=1,
       max=20, step=0.1, help="This much bought at the ask while the ask does not move vetoes."),
    _p("red_mult", "tape", "Red burst at", NUMBER, TAPE_GATE_RED_BURST_MULT, unit="x the ask volume", min=1, max=20,
       step=0.1, help="Bid-side volume over this multiple of ask-side volume waits."),

    _p("pillar_min_price", "grade", "Price pillar from", NUMBER, SETUPS_PILLAR_MIN_PRICE, unit="$", min=0.1, max=1000,
       step=0.5),
    _p("pillar_max_price", "grade", "Price pillar to", NUMBER, SETUPS_PILLAR_MAX_PRICE, unit="$", min=0.1, max=1000,
       step=0.5),
    _p("pillar_min_change_pct", "grade", "Change pillar at least", NUMBER, SETUPS_PILLAR_MIN_CHANGE_PCT, unit="%",
       min=0, max=10000, step=1),
    _p("pillar_min_rvol", "grade", "Volume pillar at least", NUMBER, SETUPS_PILLAR_MIN_RVOL, unit="x relative volume",
       min=0, max=10000, step=0.5),
    _p("pillar_max_float_m", "grade", "Float pillar at most", NUMBER, round(SETUPS_PILLAR_MAX_FLOAT / 1e6, _DECIMALS),
       unit="M shares", min=0.1, max=10000, step=1),

    _p("bot_window_start", "bot", "Bot entries from", TIME, BOT_ENTRY_WINDOW_START_ET, unit="ET", min="04:00",
       max="20:00", help="At Strategy the bot sends an entry only inside this window (the venue's clock)."),
    _p("bot_window_end", "bot", "Bot entries until", TIME, BOT_ENTRY_WINDOW_END_ET, unit="ET", min="04:00", max="20:00"),
    _p("bot_entries_per_day", "bot", "Bot entries a day", INT, BOT_ENTRIES_PER_DAY, unit="entries", min=1, max=3, step=1,
       help="Entries the bot may send in one venue day."),
)

# -- Setups without a scanner: the research harness's pre-registered numbers. -------
# Mirrors research/momentum/backtest_setups.py ``Params`` (P2 flat top, P3 red to
# green) and research/orb/backtest_gng.py ``GParams`` (A2 Gap and Go); a test
# checks the defaults against those files. Kept, not watched: no scanner reads them.
_RESEARCH_UNIVERSE: tuple[ParamSpec, ...] = (
    _p("min_price", "universe", "Price at 09:30 from", NUMBER, 2.0, unit="$", min=0.1, max=1000, step=0.5, live=False),
    _p("max_price", "universe", "Price at 09:30 to", NUMBER, 20.0, unit="$", min=0.1, max=1000, step=0.5, live=False),
    _p("min_gap_pct", "universe", "Gap at least", NUMBER, 10.0, unit="%", min=0, max=10000, step=1, live=False,
       help="09:30 open over the prior close."),
    _p("min_pm_rvol", "universe", "Pre-market relative volume at least", NUMBER, 5.0, unit="x", min=0, max=10000,
       step=0.5, live=False, help="Against the average of the prior 14 pre-markets."),
    _p("require_news", "universe", "Needs a news article", BOOL, True, live=False,
       help="At least one article since the prior close, before 09:30."),
)


def _shared_bar_rules(*, start: str, cutoff: str) -> tuple[ParamSpec, ...]:
    return (
        _p("session_start", "entry", "Enters from", TIME, start, unit="ET", min="04:00", max="20:00", live=False),
        _p("entry_cutoff", "entry", "Enters until", TIME, cutoff, unit="ET", min="04:00", max="20:00", live=False),
        _p("ema_period", "setup", "EMA", INT, 9, unit="bars", min=2, max=100, step=1, live=False),
        _p("ema_tol", "setup", "EMA slack", NUMBER, 0.0, unit="%", min=0, max=10, step=0.1, live=False),
        _p("macd_positive", "setup", "MACD histogram above zero", BOOL, True, live=False),
        _p("max_per_symbol_day", "setup", "Trades a symbol a day", INT, 2, unit="trades", min=1, max=10, step=1,
           live=False),
        _p("stop_cap", "risk", "Largest risk a share", NUMBER, 0.20, unit="$", min=0.01, max=10, step=0.01, live=False),
        _p("min_stop", "risk", "Smallest risk a share", NUMBER, 0.03, unit="$", min=0, max=5, step=0.01, live=False),
        _p("target_r", "risk", "Target 1", NUMBER, 2.0, unit="R", min=0.25, max=20, step=0.25, live=False,
           help="Half off at target 1, the stop to the entry, the rest on the first close under the EMA."),
        _p("bailout_bars", "risk", "Out after", INT, 5, unit="bars", min=1, max=120, step=1, live=False,
           help="This many candles without a close over the entry -> out at the close."),
    )


_FLAT_TOP: tuple[ParamSpec, ...] = _RESEARCH_UNIVERSE + (
    _p("ft_impulse_pct", "setup", "Impulse at least", NUMBER, 3.0, unit="%", min=0.5, max=100, step=0.5, live=False,
       help="The move into the high of day, over the leg window's lowest low."),
    _p("leg_window", "setup", "Impulse window", INT, 10, unit="bars", min=2, max=120, step=1, live=False),
    _p("ft_min_consol", "setup", "Tight candles at least", INT, 2, unit="bars", min=1, max=30, step=1, live=False),
    _p("ft_max_consol", "setup", "Tight candles at most", INT, 6, unit="bars", min=1, max=30, step=1, live=False),
    _p("ft_band", "setup", "Closes within", NUMBER, 2.0, unit="% under the high", min=0.1, max=20, step=0.1,
       live=False, help="Every consolidation close sits within this of the high of day."),
    _p("ft_entry", "entry", "Entry", CHOICE, "hold",
       choices=(("hold", "a green candle that holds over the high"), ("break", "the break of the high")), live=False),
    _p("ft_hold_bars", "entry", "Hold must come within", INT, 3, unit="bars", min=1, max=30, step=1, live=False),
) + _shared_bar_rules(start="09:30", cutoff="11:30")

_RED_TO_GREEN: tuple[ParamSpec, ...] = _RESEARCH_UNIVERSE + (
    _p("r2g_min_red_bars", "setup", "Closes under the open at least", INT, 1, unit="bars", min=1, max=60, step=1,
       live=False),
    _p("r2g_cutoff", "entry", "Reclaim by", TIME, "10:30", unit="ET", min="04:00", max="20:00", live=False),
    _p("r2g_target_hod", "risk", "Target is at least the high of day", BOOL, True, live=False),
) + _shared_bar_rules(start="09:30", cutoff="11:30")

_GAP_AND_GO: tuple[ParamSpec, ...] = _RESEARCH_UNIVERSE + (
    _p("top", "universe", "Candidates a day", INT, 10, unit="names", min=1, max=100, step=1, live=False,
       help="Ranked by pre-market relative volume."),
    _p("entry_end", "entry", "Buy stop at the pre-market high until", TIME, "10:00", unit="ET", min="09:30",
       max="16:00", live=False, help="Live from 09:30; a gap over the pre-market high at the open is skipped."),
    _p("stop_cents", "risk", "Stop at most", NUMBER, 0.20, unit="$", min=0.01, max=10, step=0.01, live=False),
    _p("stop_pct", "risk", "... or", NUMBER, 4.0, unit="% of the entry, whichever is smaller", min=0.1, max=50,
       step=0.1, live=False),
    _p("t1_r", "risk", "Target 1 (half)", NUMBER, 2.0, unit="R", min=0.25, max=20, step=0.25, live=False),
    _p("t2_r", "risk", "Target 2 (the rest)", NUMBER, 4.0, unit="R", min=0.25, max=40, step=0.25, live=False),
    _p("time_stop", "risk", "Time stop", TIME, "11:30", unit="ET", min="09:30", max="16:00", live=False),
)

CATALOGUE: dict[str, tuple[ParamSpec, ...]] = {
    BOT_SETUP_FIRST_PULLBACK: _FIRST_PULLBACK,
    BOT_SETUP_GAP_AND_GO: _GAP_AND_GO,
    BOT_SETUP_FLAT_TOP: _FLAT_TOP,
    BOT_SETUP_RED_TO_GREEN: _RED_TO_GREEN,
    BOT_SETUP_MICRO_PULLBACK: (),
}

# Where each setup's numbers come from, as the Bots page says it.
SOURCES: dict[str, str] = {
    BOT_SETUP_FIRST_PULLBACK: "The live scanner's rules (ADR 022). Every template is watched at once.",
    BOT_SETUP_GAP_AND_GO: "The research's pre-registered rules (A2). Kept for its scanner -- nothing watches them yet.",
    BOT_SETUP_FLAT_TOP: "The research's pre-registered rules (P2). Kept for its scanner -- nothing watches them yet.",
    BOT_SETUP_RED_TO_GREEN: "The research's pre-registered rules (P3). Kept for its scanner -- nothing watches them yet.",
    BOT_SETUP_MICRO_PULLBACK: "No parameters yet: it has never been tested. They are set when its one-second test (S5) is built.",
}

# Pairs that must stay in order: (low key, high key, equal allowed, message).
_ORDERED: tuple[tuple[str, str, bool, str], ...] = (
    ("min_price", "max_price", True, "the price floor is over the ceiling"),
    ("min_pullback_bars", "max_pullback_bars", True, "the shortest pullback is longer than the longest"),
    ("session_start", "entry_cutoff", False, "the arming window ends before it starts"),
    ("bot_window_start", "bot_window_end", False, "the bot's window ends before it starts"),
    ("pillar_min_price", "pillar_max_price", True, "the price pillar's floor is over its ceiling"),
    ("wall", "big_seller", True, "the seller that waits is bigger than the one that vetoes"),
    ("macd_fast", "macd_slow", False, "the MACD fast period is not shorter than the slow"),
    ("ft_min_consol", "ft_max_consol", True, "the fewest tight candles is more than the most"),
    ("t1_r", "t2_r", True, "target 1 is beyond target 2"),
)


def setup_ids() -> tuple[str, ...]:
    return tuple(BOT_SETUPS)


def has_scanner(setup_id: str) -> bool:
    return setup_id in BOT_SETUPS_WITH_SCANNER


def specs(setup_id: str) -> tuple[ParamSpec, ...]:
    try:
        return CATALOGUE[setup_id]
    except KeyError:
        raise TemplateError(f"unknown setup {setup_id!r}", code="SETUP_UNKNOWN") from None


def defaults(setup_id: str) -> dict[str, Any]:
    return {s.key: s.default for s in specs(setup_id)}


def _minutes(text: str) -> int:
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


def _coerce(spec: ParamSpec, raw: Any) -> Any:
    label = f"{spec.label} ({spec.key})"
    if raw is None:
        if spec.nullable:
            return None
        raise TemplateError(f"{label} needs a value", spec.key)
    if spec.kind == BOOL:
        if isinstance(raw, bool):
            return raw
        raise TemplateError(f"{label} is on or off (true / false)", spec.key)
    if spec.kind == TIME:
        text = str(raw).strip()
        if not _TIME_RE.match(text):
            raise TemplateError(f"{label} is a time like 07:00", spec.key)
        if spec.min is not None and _minutes(text) < _minutes(str(spec.min)):
            raise TemplateError(f"{label} is {spec.min} ET or later", spec.key)
        if spec.max is not None and _minutes(text) > _minutes(str(spec.max)):
            raise TemplateError(f"{label} is {spec.max} ET or earlier", spec.key)
        return text
    if spec.kind == CHOICE:
        allowed = [v for v, _ in spec.choices]
        if raw not in allowed:
            raise TemplateError(f"{label} is one of {', '.join(allowed)}", spec.key)
        return raw
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise TemplateError(f"{label} is a number", spec.key)
    value = float(raw)
    if not math.isfinite(value):
        raise TemplateError(f"{label} is a number", spec.key)
    if spec.kind == INT:
        if value != int(value):
            raise TemplateError(f"{label} is a whole number", spec.key)
        value = int(value)
    else:
        value = round(value, _DECIMALS)
    if spec.min is not None and value < float(spec.min):
        raise TemplateError(f"{label} is at least {spec.min:g} {spec.unit}".rstrip(), spec.key)
    if spec.max is not None and value > float(spec.max):
        raise TemplateError(f"{label} is at most {spec.max:g} {spec.unit}".rstrip(), spec.key)
    return value


def validate(setup_id: str, values: dict[str, Any] | None, *, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """A full, checked value map: ``base`` (else the defaults) with ``values`` over it.

    A key the catalogue does not list is refused, so a typo never saves as a
    silent no-op; a key the base lacks (a parameter added after the template was
    saved) takes its default -- the rule the template ran on until then.
    """
    table = {s.key: s for s in specs(setup_id)}
    merged = {**defaults(setup_id), **{k: v for k, v in (base or {}).items() if k in table}}
    for key in (values or {}):
        if key not in table:
            raise TemplateError(f"{key!r} is not a {setup_id.replace('_', ' ')} parameter", key)
    merged.update(values or {})
    out = {key: _coerce(spec, merged.get(key)) for key, spec in table.items()}
    for low, high, equal_ok, message in _ORDERED:
        if low not in table or high not in table or out[low] is None or out[high] is None:
            continue
        a, b = out[low], out[high]
        if table[low].kind == TIME:
            a, b = _minutes(a), _minutes(b)
        if a > b or (a == b and not equal_ok):
            raise TemplateError(message, high)
    return out


def fingerprint(values: dict[str, Any]) -> str:
    """A short, stable hash of a value map (the audit stamp on a scoreboard row)."""
    blob = json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def wire(setup_id: str) -> dict[str, Any]:
    """The catalogue for one setup as the Bots page draws it: groups in order."""
    groups: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    for spec in specs(setup_id):
        if spec.group not in index:
            label, blurb = GROUP_LABELS[spec.group]
            index[spec.group] = {"id": spec.group, "label": label, "blurb": blurb, "params": []}
            groups.append(index[spec.group])
        index[spec.group]["params"].append(spec.wire())
    return {"setup": setup_id, "scanner": has_scanner(setup_id), "source": SOURCES.get(setup_id, ""), "groups": groups}
