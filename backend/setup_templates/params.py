"""Every setup's parameter table (ADR 029, ADR 031): one ``ParamSpec`` per number a setup runs on.

maintainer: one-concern the parameter table of every setup the playbook lists, in the order the Bots page draws it

Pure data: no I/O, no scanner imports. One entry per setup the playbook lists
(``constants_bot.BOT_SETUPS``) -- its parameters grouped, each with a unit, bounds, and
the default that is the setup's rule. ``live`` says whether a running scanner reads the
parameter; a setup without a scanner keeps its research parameters
(``research/orb/backtest_gng.py``) for when it gets one. Every setup with a scanner (ADR
031) shares the stock filter, the tape gate, the grade and the bot's entry rules; its
pattern, entry and risk groups are its own.

Values are kept in the unit the operator types -- percent as 5, not 0.05; a float in
millions of shares -- and ``setup_scanner/lane_params.py`` converts them for the scanner
in one place. A nullable parameter is off when ``None``. ``catalogue`` checks a value
map against these tables (moved out of it 2026-10-06, when the flat top's touch
parameters took it past the size ceiling).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from constants_bot import (
    BOT_ENTRY_WINDOW_END_ET,
    BOT_ENTRY_WINDOW_START_ET,
    BOT_GRADES_CHOICES,
    BOT_GRADES_DEFAULT,
    BOT_SETUP_BULL_FLAG,
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SETUP_FLAT_TOP,
    BOT_SETUP_FLAT_TOP_5M,
    BOT_SETUP_GAP_AND_GO,
    BOT_SETUP_MICRO_PULLBACK,
    BOT_SETUP_RED_TO_GREEN,
    BOT_SETUPS_A_DAY_DEFAULT,
    BOT_SETUPS_A_DAY_MAX,
)
from constants_setups import (
    FLUSH_EXIT_EXIT,
    FLUSH_EXIT_HOLD_SEC,
    FLUSH_EXIT_MIN_R,
    FLUSH_EXIT_OFF,
    FLUSH_EXIT_TIGHTEN,
    FLUSH_EXIT_TRAIL_R,
    SETUPS_BAILOUT_BARS,
    SETUPS_BF_EMA_HOLD,
    SETUPS_BF_EMA_TOUCH_PCT,
    SETUPS_BF_FLAG_VOLUME_LIGHTER,
    SETUPS_BF_MAX_FLAG_BARS,
    SETUPS_BF_MAX_PER_SYMBOL_DAY,
    SETUPS_BF_MAX_POLE_WICK,
    SETUPS_BF_MAX_RETRACE,
    SETUPS_BF_MIN_FLAG_BARS,
    SETUPS_BF_POLE_MIN_BARS,
    SETUPS_BF_POLE_MIN_DOLLARS,
    SETUPS_BF_POLE_MIN_PCT,
    SETUPS_BF_POLE_VOLUME_RISING,
    SETUPS_BF_REJECT_RED_VOLUME_HIGH,
    SETUPS_BF_REQUIRE_HOD,
    SETUPS_EMA_PERIOD,
    SETUPS_EMA_TOLERANCE,
    SETUPS_ENTRY_CUTOFF_ET,
    SETUPS_ENTRY_OFFSET_DOLLARS,
    SETUPS_FT_BAND,
    SETUPS_FT_BASE_FIRST_TOUCH,
    SETUPS_FT_BASE_LAST_HIGH,
    SETUPS_FT_BASE_START,
    SETUPS_FT_ENTRY,
    SETUPS_FT_HOLD_BARS,
    SETUPS_FT_HOLD_STOP_CANDLE,
    SETUPS_FT_HOLD_STOP_PULLBACK,
    SETUPS_FT_IMPULSE_PCT,
    SETUPS_FT5_HOLD_BARS,
    SETUPS_FT5_HOLD_STOP,
    SETUPS_5M_ENTRY_CUTOFF_ET,
    SETUPS_FT_LEG_WINDOW_BARS,
    SETUPS_FT_MAX_CONSOL,
    SETUPS_FT_MAX_PER_SYMBOL_DAY,
    SETUPS_FT_MIN_CONSOL,
    SETUPS_FT_MIN_TOUCHES,
    SETUPS_FT_TOUCH_DOLLARS,
    SETUPS_FT_TOUCH_PCT,
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
    SETUPS_GNG_CUTOFF_ET,
    SETUPS_GNG_MACD_POSITIVE,
    SETUPS_GNG_OPEN_ET,
    SETUPS_GNG_STOP_CENTS,
    SETUPS_GNG_STOP_PCT,
    SETUPS_R2G_CUTOFF_ET,
    SETUPS_R2G_MIN_RED_BARS,
    SETUPS_R2G_OPEN_ET,
    SETUPS_R2G_TARGET_HOD,
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
    TAPE_ENTRY_BOTH,
    TAPE_ENTRY_GATE,
    TAPE_ENTRY_MIN_SCORE,
    TAPE_ENTRY_SCORE,
    TAPE_FLOW_BASELINE_SEC,
    TAPE_FLOW_BOOK_LEVELS,
    TAPE_FLOW_BURST_AT,
    TAPE_FLOW_DRIFT_FULL,
    TAPE_FLOW_FLUSH_AT,
    TAPE_FLOW_MIN_PRINTS,
    TAPE_FLOW_MIN_SHARES,
    TAPE_FLOW_PACE_FULL,
    TAPE_FLOW_W_BOOK,
    TAPE_FLOW_W_DRIFT,
    TAPE_FLOW_W_IMBALANCE,
    TAPE_FLOW_W_PACE,
    TAPE_FLOW_WINDOW_SEC,
)

NUMBER, INT, BOOL, TIME, CHOICE = "number", "int", "bool", "time", "choice"
DECIMALS = 6                      # a value's places, as the operator types it


class TemplateError(ValueError):
    """A value the catalogue refuses; ``field`` names the parameter (or None).

    ``message`` is written for the operator (it is what the API answers);
    nothing else about the error ever leaves the backend."""

    def __init__(self, message: str, field: str | None = None, code: str = "TEMPLATE_INVALID"):
        super().__init__(message)
        self.message = message
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

    def wire(self, *, affects_readout: bool = True) -> dict[str, Any]:
        return {
            "key": self.key, "group": self.group, "label": self.label, "kind": self.kind,
            "default": self.default, "unit": self.unit, "min": self.min, "max": self.max,
            "step": self.step, "choices": [{"value": v, "label": lbl} for v, lbl in self.choices],
            "nullable": self.nullable, "help": self.help, "live": self.live, "affects_readout": affects_readout,
        }


BOT_GROUP = "bot"
GROUP_LABELS: dict[str, tuple[str, str]] = {
    "stock": ("Stock filter", "Checked when a setup arms, from the Five Pillars read then. Off lets every name the scanner follows through."),
    "universe": ("Universe", "The symbol-days the research tested."),
    "setup": ("The pattern", "What the bars must show before a setup arms."),
    "entry": ("Entry", "Where the buy goes and when."),
    "risk": ("Risk and target", "The stop, the risk it allows, the target, and the scoring exit."),
    "tape": ("Tape gate", "Read from the Level 2 and time and sales when price is near the trigger."),
    "flow": ("Tape flow", "One score from -1 (sellers) to +1 (buyers): prints at the ask against the bid, how fast "
                          "they come, where price went, and the book. Read at the trigger and while a trade is on; "
                          "it can decide the entry and get out on a flush."),
    "grade": ("Five Pillars grade", "Grades every armed setup A / B / C. A pillar Nova does not know never passes."),
    BOT_GROUP: ("Bot entries at Strategy", "When and what the bot may buy while this template is in play: its window, "
                           "inside the setup's arming window, the grades and the setups a stock a day. Changing them "
                           "never starts the read-out over: the read-out scores the setup, not the bot."),
}


def minutes(text: str) -> int:
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


def _pct(fraction: float | None) -> float | None:
    return None if fraction is None else round(fraction * 100, DECIMALS)


def _p(key: str, group: str, label: str, kind: str, default: Any, **kw: Any) -> ParamSpec:
    return ParamSpec(key=key, group=group, label=label, kind=kind, default=default, **kw)


# -- Shared by every setup with a scanner: the stock filter, the tape gate, the grade,
# and the bot's entries at Strategy (ADR 029, ADR 031). One spec each, so a change to a
# unit or a bound is the same on every setup's card.
_STOCK: tuple[ParamSpec, ...] = (
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
)

_TAPE: tuple[ParamSpec, ...] = (
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
)

_FLOW: tuple[ParamSpec, ...] = (
    _p("tape_entry", "flow", "The entry reads", CHOICE, TAPE_ENTRY_GATE,
       choices=((TAPE_ENTRY_GATE, "the tape gate's prints (green at the ask, no red burst)"),
                (TAPE_ENTRY_SCORE, "the flow score instead of the print counts"),
                (TAPE_ENTRY_BOTH, "both: green prints and the flow score")),
       help="The vetoes and a seller that is not thinning hold in every mode. The gate is the pre-registered rule."),
    _p("flow_entry_min", "flow", "Entry needs a score of at least", NUMBER, TAPE_ENTRY_MIN_SCORE, unit="score",
       min=-1, max=1, step=0.05, help="Read when the entry reads the flow score."),
    _p("flush_exit", "flow", "On a flush while in", CHOICE, FLUSH_EXIT_OFF,
       choices=((FLUSH_EXIT_OFF, "nothing (the pre-registered exits)"),
                (FLUSH_EXIT_TIGHTEN, "tighten the stop under the price"),
                (FLUSH_EXIT_EXIT, "get out at the bid")),
       help="The scoring exit and Nova's bot both follow it while this template is in play."),
    _p("flush_hold_sec", "flow", "A flush counts from", NUMBER, FLUSH_EXIT_HOLD_SEC, unit="s after the entry", min=0,
       max=600, step=1, help="Red right after the entry is often the entry's own noise."),
    _p("flush_trail_r", "flow", "Tighten to", NUMBER, FLUSH_EXIT_TRAIL_R, unit="R under the price", min=0.1, max=5,
       step=0.05, help="The stop moves up to this far under the price at the flush -- never down."),
    _p("flush_min_r", "flow", "Only while up at least", NUMBER, FLUSH_EXIT_MIN_R, unit="R", min=-5, max=20,
       step=0.25, nullable=True, help="On: a flush counts only while the trade is up this much. Off: any time."),
    _p("flow_window_sec", "flow", "Reads the last", NUMBER, TAPE_FLOW_WINDOW_SEC, unit="s", min=1, max=120, step=1,
       help="The prints, the price move and the book the four readings look at."),
    _p("flow_baseline_sec", "flow", "Pace against the last", NUMBER, TAPE_FLOW_BASELINE_SEC, unit="s", min=5,
       max=1800, step=5, help="The tape's usual pace, measured before the window."),
    _p("flow_min_prints", "flow", "Needs at least", INT, TAPE_FLOW_MIN_PRINTS, unit="prints at the bid or ask", min=1,
       max=500, step=1, help="Fewer reads quiet: too little tape to say."),
    _p("flow_min_shares", "flow", "... and at least", INT, int(TAPE_FLOW_MIN_SHARES), unit="shares", min=0,
       max=10_000_000, step=100),
    _p("flow_w_imbalance", "flow", "Weight: ask vs bid", NUMBER, TAPE_FLOW_W_IMBALANCE, unit="parts", min=0, max=10,
       step=0.5, help="Shares at the ask minus shares at the bid, over both."),
    _p("flow_w_pace", "flow", "Weight: pace", NUMBER, TAPE_FLOW_W_PACE, unit="parts", min=0, max=10, step=0.5,
       help="How fast the tape runs against its usual pace, in the direction of the imbalance."),
    _p("flow_w_drift", "flow", "Weight: price move", NUMBER, TAPE_FLOW_W_DRIFT, unit="parts", min=0, max=10, step=0.5,
       help="Where the price went inside the window."),
    _p("flow_w_book", "flow", "Weight: the book", NUMBER, TAPE_FLOW_W_BOOK, unit="parts", min=0, max=10, step=0.5,
       help="Displayed bid shares minus ask shares near the inside."),
    _p("flow_pace_full", "flow", "Pace reads full at", NUMBER, TAPE_FLOW_PACE_FULL, unit="x the usual pace", min=1.1,
       max=50, step=0.1),
    _p("flow_drift_full_pct", "flow", "Price move reads full at", NUMBER, _pct(TAPE_FLOW_DRIFT_FULL), unit="%",
       min=0.05, max=20, step=0.05),
    _p("flow_book_levels", "flow", "Book reads", INT, TAPE_FLOW_BOOK_LEVELS, unit="prices a side", min=1, max=20,
       step=1),
    _p("flow_burst_at", "flow", "Burst at a score of", NUMBER, TAPE_FLOW_BURST_AT, unit="or more", min=0.05, max=1,
       step=0.05),
    _p("flow_flush_at", "flow", "Flush at a score of minus", NUMBER, TAPE_FLOW_FLUSH_AT, unit="or less", min=0.05,
       max=1, step=0.05),
)

_GRADE: tuple[ParamSpec, ...] = (
    _p("pillar_min_price", "grade", "Price pillar from", NUMBER, SETUPS_PILLAR_MIN_PRICE, unit="$", min=0.1, max=1000,
       step=0.5),
    _p("pillar_max_price", "grade", "Price pillar to", NUMBER, SETUPS_PILLAR_MAX_PRICE, unit="$", min=0.1, max=1000,
       step=0.5),
    _p("pillar_min_change_pct", "grade", "Change pillar at least", NUMBER, SETUPS_PILLAR_MIN_CHANGE_PCT, unit="%",
       min=0, max=10000, step=1),
    _p("pillar_min_rvol", "grade", "Volume pillar at least", NUMBER, SETUPS_PILLAR_MIN_RVOL, unit="x relative volume",
       min=0, max=10000, step=0.5),
    _p("pillar_max_float_m", "grade", "Float pillar at most", NUMBER, round(SETUPS_PILLAR_MAX_FLOAT / 1e6, DECIMALS),
       unit="M shares", min=0.1, max=10000, step=1),
)

def _bot(arm_start: str, arm_end: str) -> tuple[ParamSpec, ...]:
    """The bot's rules (ADR 044): its entry window -- the material's 07:00-10:00, inside the setup's
    arming window (``arm_start``-``arm_end``; red to green arms 09:30-10:30, so 09:30-10:00) -- the
    grades it buys and how many setups of a stock a day."""
    start = max(BOT_ENTRY_WINDOW_START_ET, arm_start, key=minutes)
    end = min(BOT_ENTRY_WINDOW_END_ET, arm_end, key=minutes)
    return (
        _p("bot_window_start", BOT_GROUP, "Bot entries from", TIME, start, unit="ET", min="04:00", max="20:00",
           help="At Strategy the bot sends an entry only inside this window (the venue's clock). It sits inside "
                "the arming window; changing it never starts the read-out over."),
        _p("bot_window_end", BOT_GROUP, "Bot entries until", TIME, end, unit="ET", min="04:00", max="20:00",
           help="No bot entry at or after this time. The bot's entries a day are the sleeve's (Bots page)."),
        _p("bot_grades", BOT_GROUP, "Grades Nova buys", CHOICE, BOT_GRADES_DEFAULT, choices=BOT_GRADES_CHOICES,
           help="Nova buys this setup only at these grades. C is never a trade."),
        _p("bot_setups_a_day", BOT_GROUP, "Setups a stock a day", INT, BOT_SETUPS_A_DAY_DEFAULT, unit="setups",
           min=1, max=BOT_SETUPS_A_DAY_MAX, step=1,
           help="1: Nova buys only the 1st of this setup on a stock that day. 2: the 1st and the 2nd."),
    )


_BOT = _bot(SETUPS_SESSION_START_ET, SETUPS_ENTRY_CUTOFF_ET)


def _ema(hold_help: str, tol_help: str | None = None) -> tuple[ParamSpec, ...]:
    """The EMA period (and its slack, unless ``tol_help`` is None: the setup reads no slack)."""
    period = _p("ema_period", "setup", "Holds the EMA", INT, SETUPS_EMA_PERIOD, unit="bars", min=2, max=100, step=1,
                help=hold_help)
    if tol_help is None:
        return (period,)
    return (period, _p("ema_tol", "setup", "EMA slack", NUMBER, _pct(SETUPS_EMA_TOLERANCE), unit="%", min=0, max=10,
                       step=0.1, help=tol_help))


def _macd(help_text: str) -> tuple[ParamSpec, ...]:
    return (
        _p("macd_positive", "setup", "MACD histogram above zero", BOOL, SETUPS_MACD_POSITIVE, help=help_text),
        _p("macd_fast", "setup", "MACD fast", INT, SETUPS_MACD_FAST, unit="bars", min=2, max=60, step=1),
        _p("macd_slow", "setup", "MACD slow", INT, SETUPS_MACD_SLOW, unit="bars", min=3, max=120, step=1),
        _p("macd_signal", "setup", "MACD signal", INT, SETUPS_MACD_SIGNAL, unit="bars", min=2, max=60, step=1),
    )


def _near() -> tuple[ParamSpec, ...]:
    return (
        _p("near_dollars", "entry", "Near the trigger within", NUMBER, SETUPS_NEAR_DOLLARS, unit="$", min=0, max=2,
           step=0.01, help="Price this close to the trigger is when the tape is read (or the percent below, whichever is wider)."),
        _p("near_pct", "entry", "... or within", NUMBER, _pct(SETUPS_NEAR_PCT), unit="%", min=0, max=10, step=0.05),
    )


def _window(start_label: str, start_help: str, cutoff_help: str) -> tuple[ParamSpec, ...]:
    return (
        _p("session_start", "entry", start_label, TIME, SETUPS_SESSION_START_ET, unit="ET", min="04:00", max="20:00",
           help=start_help),
        _p("entry_cutoff", "entry", "Arms until", TIME, SETUPS_ENTRY_CUTOFF_ET, unit="ET", min="04:00", max="20:00",
           help=cutoff_help),
    )


def _risk(stop_help: str) -> tuple[ParamSpec, ...]:
    return (
        _p("stop_cap", "risk", "Largest risk a share", NUMBER, SETUPS_STOP_CAP_DOLLARS, unit="$", min=0.01, max=10,
           step=0.01, help=stop_help),
        _p("min_stop", "risk", "Smallest risk a share", NUMBER, SETUPS_MIN_STOP_DOLLARS, unit="$", min=0, max=5, step=0.01,
           help="A smaller risk skips the setup: the stop would sit in the spread."),
        _p("risk_slippage", "risk", "Slippage counted in the risk", NUMBER, SETUPS_RISK_SLIPPAGE_DOLLARS, unit="$", min=0,
           max=1, step=0.01, help="Added to the risk before the two checks above, as the research did."),
    )


_TARGET_R = _p("target_r", "risk", "R multiple", NUMBER, SETUPS_TARGET_R, unit="R", min=0.25, max=20, step=0.25,
               help="Target 1 at R x the risk over the entry.")
_TARGET_FIXED = _p("target_fixed", "risk", "Fixed target", NUMBER, SETUPS_TARGET_FIXED_DOLLARS, unit="$", min=0.01,
                   max=10, step=0.01, help="Used when target 1 is a fixed amount over the entry.")
_BAILOUT = _p("bailout_bars", "risk", "Out after", INT, SETUPS_BAILOUT_BARS, unit="bars", min=1, max=120, step=1,
              help="Scoring exit: this many candles without a close over the entry -> out at the close.")


# -- First pullback: the live scanner's numbers (constants_setups, ADR 022). --------
_FIRST_PULLBACK: tuple[ParamSpec, ...] = _STOCK + (
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
) + _ema("Every pullback candle closes at or above this EMA.",
                                                   "A pullback close may sit this far under the EMA.") + _macd(
    "The last pullback candle's MACD histogram is above zero (the front side of the move).") + (
    _p("max_per_symbol_day", "setup", "Setups a symbol a day", INT, SETUPS_MAX_PER_SYMBOL_DAY, unit="setups", min=1,
       max=10, step=1, help="The first pullback, then the second -- no more on one symbol that day."),
    _p("entry_offset", "entry", "Buy over the pullback high by", NUMBER, SETUPS_ENTRY_OFFSET_DOLLARS, unit="$", min=0,
       max=1, step=0.01, help="The entry is the last pullback candle's high plus this."),
) + _window("Arms from", "No setup arms before this time.",
            "No setup arms, and none triggers, at or after this time.") + _near() + _risk(
    "Entry minus the pullback low. A bigger risk skips the setup.") + (
    _p("target_mode", "risk", "Target 1", CHOICE, SETUPS_TARGET_MODE,
       choices=(("leg_or_r", "the leg high or R x risk, whichever is higher"), ("fixed", "a fixed amount over the entry")),
       help="Half comes off at target 1 and the stop moves to the entry (the scoring exit)."),
    _p("target_r", "risk", "R multiple", NUMBER, SETUPS_TARGET_R, unit="R", min=0.25, max=20, step=0.25,
       help="Used when target 1 is the leg high or R x risk."),
    _TARGET_FIXED, _BAILOUT,
) + _TAPE + _FLOW + _GRADE + _BOT

# -- Bull flag (ADR 031): pre-registered from the operator's material. ------------------
_BULL_FLAG: tuple[ParamSpec, ...] = _STOCK + (
    _p("pole_min_bars", "setup", "Pole at least", INT, SETUPS_BF_POLE_MIN_BARS, unit="green candles", min=1, max=20,
       step=1, help="Consecutive green candles (close over open) ending at the pole top."),
    _p("pole_min_pct", "setup", "Pole rise at least", NUMBER, _pct(SETUPS_BF_POLE_MIN_PCT), unit="%", min=0.5, max=100,
       step=0.5, help="From the pole's lowest low to its highest high (or the dollars below, whichever the pole makes)."),
    _p("pole_min_dollars", "setup", "... or at least", NUMBER, SETUPS_BF_POLE_MIN_DOLLARS, unit="$", min=0.01, max=10,
       step=0.01, nullable=True, help="A pole that rose this many dollars qualifies even under the percent. Off: the percent only."),
    _p("pole_volume_rising", "setup", "Pole volume rising", BOOL, SETUPS_BF_POLE_VOLUME_RISING,
       help="The last pole candle trades at least the first's volume (a tiring pole is skipped)."),
    _p("min_flag_bars", "setup", "Flag at least", INT, SETUPS_BF_MIN_FLAG_BARS, unit="candles", min=1, max=10, step=1,
       help="Red (or doji) candles after the pole top. One is a micro pullback, not a flag."),
    _p("max_flag_bars", "setup", "Flag at most", INT, SETUPS_BF_MAX_FLAG_BARS, unit="candles", min=1, max=10, step=1,
       help="More red candles than this is too much selling: the setup fails."),
    _p("max_retrace", "setup", "Flag gives back at most", NUMBER, _pct(SETUPS_BF_MAX_RETRACE), unit="% of the pole",
       min=5, max=100, step=5, help="The flag's low gives back no more than this share of the pole."),
    _p("flag_volume_lighter", "setup", "Flag on lighter volume", BOOL, SETUPS_BF_FLAG_VOLUME_LIGHTER,
       help="The flag's average volume is under the pole's. Heavy selling in the flag is distribution."),
) + _ema("Every flag candle closes at or above this EMA (when the switch below is on).",
         "A flag close may sit this far under the EMA.") + (
    _p("ema_hold", "setup", "Flag closes hold the EMA", BOOL, SETUPS_BF_EMA_HOLD,
       help="Off: a flag close under the EMA does not fail the setup."),
    _p("ema_touch_pct", "setup", "Flag low near the EMA within", NUMBER, SETUPS_BF_EMA_TOUCH_PCT, unit="%", min=0.1,
       max=20, step=0.1, nullable=True,
       help="The material's perfect flag pulls back to the 9 EMA. On: the flag low must come this close to it."),
    _p("reject_red_volume_high", "setup", "Skip when the biggest-volume candle is red", BOOL,
       SETUPS_BF_REJECT_RED_VOLUME_HIGH, help="The day's highest-volume candle so far being red means sellers own the day."),
    _p("max_pole_wick", "setup", "Pole top's upper wick at most", NUMBER, _pct(SETUPS_BF_MAX_POLE_WICK),
       unit="% of its range", min=5, max=100, step=5, nullable=True,
       help="A big topping tail on the pole's last candle is a caution in the material. Off: no wick check."),
    _p("require_hod", "setup", "Pole high is the high of day", BOOL, SETUPS_BF_REQUIRE_HOD,
       help="On: the pole must set the day's high so far. The material does not ask it."),
) + _macd("The last flag candle's MACD histogram is above zero (the front side of the move).") + (
    _p("max_per_symbol_day", "setup", "Flags a symbol a day", INT, SETUPS_BF_MAX_PER_SYMBOL_DAY, unit="setups", min=1,
       max=10, step=1, help="The first and second flag -- the material skips the third."),
    _p("entry_offset", "entry", "Buy over the last flag candle's high by", NUMBER, SETUPS_ENTRY_OFFSET_DOLLARS, unit="$",
       min=0, max=1, step=0.01, help="The first candle to make a new high trades through it: the entry is that high plus this."),
) + _window("Arms from", "No flag arms before this time.",
            "No flag arms, and none triggers, at or after this time.") + _near() + _risk(
    "Entry minus the flag low. A bigger risk skips the setup.") + (
    _p("target_mode", "risk", "Target 1", CHOICE, SETUPS_TARGET_MODE,
       choices=(("leg_or_r", "the pole high or R x risk, whichever is higher"),
                ("leg", "the pole high (the material's first target)"), ("fixed", "a fixed amount over the entry")),
       help="Half comes off at target 1 and the stop moves to the entry (the scoring exit)."),
    _p("target_r", "risk", "R multiple", NUMBER, SETUPS_TARGET_R, unit="R", min=0.25, max=20, step=0.25,
       help="Used when target 1 is the pole high or R x risk (and when the pole high is not above the entry)."),
    _TARGET_FIXED, _BAILOUT,
) + _TAPE + _FLOW + _GRADE + _BOT

# -- Flat-top breakout (ADR 031; amended 2026-10-06: the high of day tapped again and again, as the operator's
# material draws it). The research's P2 rule (``find_flat_top``) is the "last_high" base with one touch and no
# tolerance -- the values a template saved before these parameters runs (``LEGACY``).
_FLAT_TOP: tuple[ParamSpec, ...] = _STOCK + (
    _p("ft_impulse_pct", "setup", "Impulse at least", NUMBER, _pct(SETUPS_FT_IMPULSE_PCT), unit="%", min=0.5, max=100,
       step=0.5, help="The move into the flat top, over the lowest low of the impulse window."),
    _p("leg_window", "setup", "Impulse window", INT, SETUPS_FT_LEG_WINDOW_BARS, unit="bars", min=2, max=120, step=1,
       help="The candles ending at the first touch the impulse is measured over."),
    _p("ft_min_touches", "setup", "Touches at least", INT, SETUPS_FT_MIN_TOUCHES, unit="candles", min=1, max=10,
       step=1, help="Candles whose high reached the flat top, the first one included: the level is tapped again and "
                    "again before it breaks. Two is a double top. From its second touch it is drawn forming."),
    _p("ft_touch_pct", "setup", "A touch is within", NUMBER, _pct(SETUPS_FT_TOUCH_PCT), unit="% under the high",
       min=0, max=5, step=0.1,
       help="A high this close under the high of day touched it, or within the dollars below, whichever is more: a "
            "real flat top is never perfect. A candle a little over the earlier touches, inside this, is a touch too."),
    _p("ft_touch_dollars", "setup", "... or within", NUMBER, SETUPS_FT_TOUCH_DOLLARS, unit="$", min=0, max=1, step=0.01),
    _p("ft_base_start", "setup", "The base starts", CHOICE, SETUPS_FT_BASE_START,
       choices=((SETUPS_FT_BASE_FIRST_TOUCH, "at the first candle that touched the flat top"),
                (SETUPS_FT_BASE_LAST_HIGH, "after the last candle at the high (the research's P2)")),
       help="First touch: the flat top runs from the first candle that reached it, every touch counted. Last high: "
            "the research's rule, the base right after the last candle at the high."),
    _p("ft_min_consol", "setup", "Base at least", INT, SETUPS_FT_MIN_CONSOL, unit="candles", min=1, max=30, step=1,
       help="Candles after the first touch, none making a high past the tolerance."),
    _p("ft_max_consol", "setup", "Base at most", INT, SETUPS_FT_MAX_CONSOL, unit="candles", min=1, max=60, step=1,
       help="A flat top that began longer ago is stale: the setup fails."),
    _p("ft_band", "setup", "Base closes within", NUMBER, _pct(SETUPS_FT_BAND), unit="% under the high", min=0.1, max=20,
       step=0.1, help="Every base close sits within this of the high of day: a flat top, not a pullback."),
) + _ema("Every base candle's low is at or above this EMA.",
                                                          "A base low may sit this far under the EMA.") + _macd(
    "The last base candle's MACD histogram is above zero (the front side of the move).") + (
    _p("max_per_symbol_day", "setup", "Setups a symbol a day", INT, SETUPS_FT_MAX_PER_SYMBOL_DAY, unit="setups", min=1,
       max=10, step=1, help="Breakouts that may trigger on one symbol in a day."),
    _p("ft_entry", "entry", "Entry", CHOICE, SETUPS_FT_ENTRY,
       choices=(("hold", "a green candle that holds over the high (the taught way)"), ("break", "the break of the high")),
       help="Hold: after the break, buy the close of the first candle that holds the flat top (its low in the touch "
            "zone or over it) and closes green over the high. Break: buy the break itself."),
    _p("ft_hold_bars", "entry", "Hold must come within", INT, SETUPS_FT_HOLD_BARS, unit="candles", min=1, max=30, step=1,
       help="Hold entry: candles after the break's own candle before the setup disarms."),
    _p("entry_offset", "entry", "Buy over by", NUMBER, SETUPS_ENTRY_OFFSET_DOLLARS, unit="$", min=0, max=1, step=0.01,
       help="Break: over the high of day by this. Hold: over the hold candle's close by this (the research's cent of slippage)."),
) + _window("Arms from", "No base arms before this time (the research began at 09:30).",
            "No base arms, and no break triggers, at or after this time.") + _near() + _risk(
    "Break: entry minus the base low. Hold: entry minus the hold candle's low. A bigger risk skips the setup.") + (
    _p("target_mode", "risk", "Target 1", CHOICE, "r",
       choices=(("r", "R x risk over the entry (the research's)"), ("fixed", "a fixed amount over the entry")),
       help="Half comes off at target 1 and the stop moves to the entry (the scoring exit)."),
    _TARGET_R, _TARGET_FIXED, _BAILOUT,
) + _TAPE + _FLOW + _GRADE + _BOT

# -- The 5-minute flat top (ADR 031 amendment 2026-10-06): the flat top's parameters read on 5-minute
# candles, the hold on the 1-minute candles after the break (``setup_scanner/flat_top_5m.py``). ----------
_FIVE = "5-min candles"
_FLAT_TOP_5M_CHANGES: dict[str, dict[str, Any]] = {
    "ft_impulse_pct": {"help": "The move into the flat top, over the lowest low of the impulse window (5-minute "
                               "candles)."},
    "leg_window": {"unit": _FIVE, "help": "The 5-minute candles ending at the first touch the impulse is measured "
                                          "over."},
    "ft_min_touches": {"unit": _FIVE, "help": "5-minute candles whose high reached the flat top, the first one "
                                              "included: the level is tapped again and again before it breaks. "
                                              "From its second touch it is drawn forming."},
    "ft_min_consol": {"unit": _FIVE, "help": "5-minute candles after the first touch, none making a high past the "
                                             "tolerance."},
    "ft_max_consol": {"unit": _FIVE},
    "ft_band": {"help": "Every 5-minute base close sits within this of the high of day: a flat top, not a pullback."},
    "ema_period": {"unit": _FIVE, "help": "Every 5-minute base candle's low is at or above this EMA of the 5-minute "
                                          "closes (the scoring exit reads the 1-minute EMA: the trade is a 1-minute "
                                          "one)."},
    "macd_positive": {"help": "The last 5-minute base candle's MACD histogram is above zero (the front side of the "
                              "move)."},
    "macd_fast": {"unit": _FIVE},
    "macd_slow": {"unit": _FIVE},
    "macd_signal": {"unit": _FIVE},
    "ft_entry": {"choices": (("hold", "a 1-minute candle that holds over the high (the taught way)"),
                             ("break", "the break of the high")),
                 "help": "Hold: after the break, buy the close of the first 1-minute candle that holds the flat top "
                         "(its low in the touch zone or over it) and closes green over the high -- the 1-minute "
                         "pullback your material buys inside the 5-minute breakout candle. Break: buy the break "
                         "itself."},
    "ft_hold_bars": {"default": SETUPS_FT5_HOLD_BARS, "unit": "minutes",
                     "help": "Hold entry: 1-minute candles after the break's own minute before the setup disarms "
                             "(five: the 5-minute breakout candle)."},
    "entry_offset": {"help": "Break: over the high of day by this. Hold: over the hold minute's close by this."},
    "entry_cutoff": {"default": SETUPS_5M_ENTRY_CUTOFF_ET,
                     "help": "No flat top arms, and no break triggers, at or after this time (slow movers set up "
                             "later in the day too)."},
    "stop_cap": {"help": "Hold: entry minus the stop (the stop below). Break: entry minus the 5-minute base low. A "
                         "bigger risk skips the setup."},
    "bailout_bars": {"unit": "minutes", "help": "Scoring exit: this many 1-minute candles without a close over the "
                                                "entry -> out at the close."},
}
_HOLD_STOP = _p("ft_hold_stop", "entry", "Hold stop", CHOICE, SETUPS_FT5_HOLD_STOP,
                choices=((SETUPS_FT_HOLD_STOP_PULLBACK, "the pullback's low: every minute since the break's"),
                         (SETUPS_FT_HOLD_STOP_CANDLE, "the hold minute's low")),
                help="Pullback: the lowest low of the minutes after the break's own, the hold included -- where the "
                     "pullback went. Candle: the hold minute's low alone, as the 1-minute flat top does.")


def _flat_top_5m() -> tuple[ParamSpec, ...]:
    """The flat top's specs with the 5-minute words and defaults, and the hold's stop after its window."""
    out: list[ParamSpec] = []
    for spec in _FLAT_TOP:
        out.append(dataclasses.replace(spec, **_FLAT_TOP_5M_CHANGES.get(spec.key, {})))
        if spec.key == "ft_hold_bars":
            out.append(_HOLD_STOP)
    return tuple(out)


_FLAT_TOP_5M = _flat_top_5m()

# -- Red to green (P3, ``find_red_to_green``): the open, then back through it. ----------
_RED_TO_GREEN: tuple[ParamSpec, ...] = _STOCK + (
    _p("r2g_min_red_bars", "setup", "Closes under the open at least", INT, SETUPS_R2G_MIN_RED_BARS, unit="candles", min=1,
       max=60, step=1, help="Counted from the opening candle; the last close must be under the open too."),
) + _ema("The scoring exit's EMA (red to green reads no EMA to arm).") + _macd(
    "The last red candle's MACD histogram is above zero. A reclaim with it under zero is not a try.") + (
    _p("session_start", "entry", "The open at", TIME, SETUPS_R2G_OPEN_ET, unit="ET", min="04:00", max="16:00",
       help="The level is the open of the first candle at or after this time."),
    _p("r2g_cutoff", "entry", "Reclaim by", TIME, SETUPS_R2G_CUTOFF_ET, unit="ET", min="04:00", max="20:00",
       help="Nothing arms, and nothing triggers, at or after this time. One try a day before it."),
    _p("entry_offset", "entry", "Buy over the open by", NUMBER, SETUPS_ENTRY_OFFSET_DOLLARS, unit="$", min=0, max=1,
       step=0.01, help="The entry is the open plus this (the bar's open when it gapped over)."),
) + _near() + _risk("Entry minus the lowest low since the open. A reclaim with a bigger risk spends the day's try.") + (
    _TARGET_R,
    _p("r2g_target_hod", "risk", "Target is at least the high of day", BOOL, SETUPS_R2G_TARGET_HOD,
       help="On: target 1 is the high of day when that is higher than R x risk."),
    _BAILOUT,
) + _TAPE + _FLOW + _GRADE + _bot(SETUPS_R2G_OPEN_ET, SETUPS_R2G_CUTOFF_ET)

# -- Gap and Go (A2, research/orb/backtest_gng.py ``GParams``, rules of 2026-09-22): the
# pre-market high, broken after the open (ADR 031 amendment 2026-10-02). A test checks the
# defaults against that file. The research picked its names by the Five Pillars at 09:30
# ranked by pre-market relative volume; the live scanner reads the names it follows, like
# every other setup, and grades them.
_GAP_AND_GO: tuple[ParamSpec, ...] = _STOCK + _ema("The scoring exit's EMA (Gap and Go reads no EMA to arm).") + (
    _p("macd_positive", "setup", "MACD histogram above zero", BOOL, SETUPS_GNG_MACD_POSITIVE,
       help="Off (the research's rule): arm at the open. On: arm only once the last candle's histogram is above zero."),
    _p("macd_fast", "setup", "MACD fast", INT, SETUPS_MACD_FAST, unit="bars", min=2, max=60, step=1),
    _p("macd_slow", "setup", "MACD slow", INT, SETUPS_MACD_SLOW, unit="bars", min=3, max=120, step=1),
    _p("macd_signal", "setup", "MACD signal", INT, SETUPS_MACD_SIGNAL, unit="bars", min=2, max=60, step=1),
    _p("session_start", "entry", "The open at", TIME, SETUPS_GNG_OPEN_ET, unit="ET", min="04:00", max="16:00",
       help="Candles before this make the pre-market high; the first price at or after it is the open. An open at "
            "or over the pre-market high skips the day."),
    _p("entry_cutoff", "entry", "Buy the break until", TIME, SETUPS_GNG_CUTOFF_ET, unit="ET", min="04:00", max="20:00",
       help="Nothing arms, and nothing triggers, at or after this time. One try a day."),
    _p("entry_offset", "entry", "Buy over the pre-market high by", NUMBER, SETUPS_ENTRY_OFFSET_DOLLARS, unit="$", min=0,
       max=1, step=0.01, help="The entry is the pre-market high plus this (the bar's open when it gapped over)."),
) + _near() + (
    _p("stop_cents", "risk", "Stop at most", NUMBER, SETUPS_GNG_STOP_CENTS, unit="$ under the entry", min=0.01, max=10,
       step=0.01, help="The stop sits this far under the entry, or the percent below, whichever is smaller."),
    _p("stop_pct", "risk", "... or", NUMBER, _pct(SETUPS_GNG_STOP_PCT), unit="% of the entry, whichever is smaller",
       min=0.1, max=50, step=0.1),
    _p("min_stop", "risk", "Smallest risk a share", NUMBER, SETUPS_MIN_STOP_DOLLARS, unit="$", min=0, max=5, step=0.01,
       help="A smaller risk skips the day: the stop would sit in the spread."),
    _p("risk_slippage", "risk", "Slippage counted in the risk", NUMBER, SETUPS_RISK_SLIPPAGE_DOLLARS, unit="$", min=0,
       max=1, step=0.01, help="Added to the risk before the check above, as the research did."),
    _TARGET_R, _BAILOUT,
) + _TAPE + _FLOW + _GRADE + _bot(SETUPS_GNG_OPEN_ET, SETUPS_GNG_CUTOFF_ET)

CATALOGUE: dict[str, tuple[ParamSpec, ...]] = {
    BOT_SETUP_FIRST_PULLBACK: _FIRST_PULLBACK,
    BOT_SETUP_BULL_FLAG: _BULL_FLAG,
    BOT_SETUP_FLAT_TOP: _FLAT_TOP,
    BOT_SETUP_FLAT_TOP_5M: _FLAT_TOP_5M,
    BOT_SETUP_RED_TO_GREEN: _RED_TO_GREEN,
    BOT_SETUP_GAP_AND_GO: _GAP_AND_GO,
    BOT_SETUP_MICRO_PULLBACK: (),
}

# Where each setup's numbers come from, as the Bots page says it.
SOURCES: dict[str, str] = {
    BOT_SETUP_FIRST_PULLBACK: "The live scanner's rules (ADR 022). Every template is watched at once.",
    BOT_SETUP_BULL_FLAG: ("The live scanner's rules, pre-registered in ADR 031 from your material -- never tested on "
                          "bars; its read-out is its first test. Every template is watched at once."),
    BOT_SETUP_FLAT_TOP: ("The live scanner reads the flat top as your material draws it (ADR 031, amended 2026-10-06): "
                         "the high of day tapped again and again within a tolerance, then the break. The research's P2 "
                         "rule is the last-high base with one touch and no tolerance. It arms from 07:00. Every "
                         "template is watched at once."),
    BOT_SETUP_FLAT_TOP_5M: ("The flat top read on 5-minute candles, as your material reads it, and bought the way it "
                            "executes it: after the break, the first 1-minute candle that holds the level and closes "
                            "green (ADR 031, amended 2026-10-06). Its read-out is its first live test. It arms "
                            "07:00-15:30. Every template is watched at once."),
    BOT_SETUP_RED_TO_GREEN: ("The live scanner reads the research's pre-registered rules (P3, ADR 031). Every template "
                             "is watched at once."),
    BOT_SETUP_GAP_AND_GO: ("The live scanner reads the research's pre-registered rules (A2, ADR 031 amendment): the break "
                           "of the pre-market high from the open until 10:00. Every template is watched at once."),
    BOT_SETUP_MICRO_PULLBACK: "No parameters yet: it has never been tested. They are set when its one-second test (S5) is built.",
}
