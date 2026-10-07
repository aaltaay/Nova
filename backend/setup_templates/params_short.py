"""The five short setups' parameter tables (ADR 049; its step 4 section names the CHOSEN numbers).

maintainer: one-concern the short setups' parameter tables, the long groups' words mirrored

Pure data, like ``params.py``, whose shared groups these reuse with their words mirrored: the stock filter
(without "Needs a catalyst": a short's news is its grade's bad-news pillar), the tape gate (the template keys
are the long's -- ``big_seller`` is the buyer that vetoes at the level), the flow (a burst of buying is a
short's flush), the bot's group. A short's grade has its own three thresholds (``pillar_min_run_pct``,
``pillar_min_fade_pct``, ``pillar_borrow_mult``), and a breakdown template's ``ssr`` trades or skips a setup
armed under SSR. ``catalogue.py`` merges these tables with the long ones.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from constants_bot import (
    BOT_SETUP_BACKSIDE,
    BOT_SETUP_BEAR_FLAG,
    BOT_SETUP_FAILED_BREAKOUT,
    BOT_SETUP_LOST_VWAP,
    BOT_SETUP_SSR_BOUNCE,
)
from constants_setups import (
    SETUPS_EMA_PERIOD,
    SETUPS_EMA_TOLERANCE,
    SETUPS_MACD_FAST,
    SETUPS_MACD_SIGNAL,
    SETUPS_MACD_SLOW,
)
from constants_short_setups import (
    SETUPS_SSR_SKIP,
    SETUPS_SSR_TRADE,
    SHORT_BACKSIDE_CUTOFF_ET,
    SHORT_BACKSIDE_FADE_LOOKBACK,
    SHORT_BACKSIDE_FADE_PCT,
    SHORT_BACKSIDE_MAX_BOUNCE_BARS,
    SHORT_BACKSIDE_MAX_RETRACE,
    SHORT_BACKSIDE_MIN_BOUNCE_BARS,
    SHORT_BEAR_FLAG_CUTOFF_ET,
    SHORT_BF_EMA_HOLD,
    SHORT_BF_FLAG_VOLUME_LIGHTER,
    SHORT_BF_MAX_FLAG_BARS,
    SHORT_BF_MAX_POLE_WICK,
    SHORT_BF_MAX_RETRACE,
    SHORT_BF_MIN_FLAG_BARS,
    SHORT_BF_POLE_MIN_BARS,
    SHORT_BF_POLE_MIN_PCT,
    SHORT_BF_POLE_VOLUME_RISING,
    SHORT_BF_REJECT_GREEN_VOLUME_HIGH,
    SHORT_ENTRY_OFFSET_DOLLARS,
    SHORT_FAILED_BREAKOUT_CUTOFF_ET,
    SHORT_FB_FAIL_BARS,
    SHORT_FB_LOOKBACK,
    SHORT_FB_MACD_NEGATIVE,
    SHORT_FB_MIN_TOUCHES,
    SHORT_FB_POKE_DOLLARS,
    SHORT_FB_TOUCH_DOLLARS,
    SHORT_FB_TOUCH_PCT,
    SHORT_FB_TRIGGER_BARS,
    SHORT_LOST_VWAP_CUTOFF_ET,
    SHORT_LOST_VWAP_OPEN_ET,
    SHORT_LV_MACD_NEGATIVE,
    SHORT_LV_RETEST_DOLLARS,
    SHORT_LV_RETEST_PCT,
    SHORT_MACD_NEGATIVE,
    SHORT_MAX_PER_SYMBOL_DAY,
    SHORT_PILLAR_BORROW_MULT,
    SHORT_PILLAR_MIN_FADE_PCT,
    SHORT_PILLAR_MIN_RUN_PCT,
    SHORT_SSR_ARM_PCT,
    SHORT_SSR_BOUNCE_CUTOFF_ET,
    SHORT_SSR_BOUNCE_GREENS,
    SHORT_SSR_CANCEL_MIN,
    SHORT_SSR_DROP_LOOKBACK,
    SHORT_SSR_DROP_PCT,
    SHORT_SSR_ROUND_STEP,
    SHORT_SSR_STOP_MIN_DOLLARS,
    SHORT_SSR_STOP_PCT,
    SHORT_STOP_OFFSET_DOLLARS,
    SHORT_WINDOW_START_ET,
)
from setup_templates.params import (
    _BAILOUT,
    _FLOW,
    _STOCK,
    _TAPE,
    _TARGET_R,
    BOOL,
    CHOICE,
    INT,
    NUMBER,
    TIME,
    ParamSpec,
    _bot,
    _near,
    _p,
    _pct,
)

GRADE_SHORT = "grade_short"     # the short grade's group (its own label: the pillars differ)


def _mirror(specs: tuple[ParamSpec, ...], words: dict[str, dict[str, Any]]) -> tuple[ParamSpec, ...]:
    return tuple(dataclasses.replace(s, **words.get(s.key, {})) for s in specs)


# -- The long groups' words, mirrored. The keys stay the long's: a short's reading of each is in its words.
_STOCK_SHORT = tuple(s for s in _STOCK if s.key != "require_catalyst")
_TAPE_SHORT = _mirror(_TAPE, {
    "spread_max": {"help": "A wider spread vetoes (or the percent below, whichever is wider)."},
    "spread_max_pct": {"unit": "% of the bid"},
    "band": {"label": "At the level down to", "unit": "$ under the trigger",
             "help": "Bid levels from 1 cent over the trigger down to this far under it are at the level."},
    "big_seller": {"label": "Buyer that vetoes", "help": "A displayed buyer this big at the level vetoes the short."},
    "wall": {"label": "Buyer that waits", "help": "A buyer this big at the level waits until it thins."},
    "thin_fraction": {"help": "The buyer shrank by this much inside the window."},
    "min_ask_prints": {"label": "Red tape needs", "unit": "prints at the bid",
                       "help": "And more volume at the bid than at the ask."},
    "hidden_mult": {"label": "Hidden buyer at", "unit": "x the inside bid",
                    "help": "This much sold at the bid while the bid does not move vetoes."},
    "red_mult": {"label": "Green burst at", "unit": "x the bid volume",
                 "help": "Ask-side volume over this multiple of bid-side volume waits."},
})
_FLOW_SHORT = _mirror(_FLOW, {
    "tape_entry": {"choices": (("gate", "the tape gate's prints (red at the bid, no green burst)"),
                               ("score", "the flow score instead of the print counts"),
                               ("both", "both: red prints and the flow score")),
                   "help": "The vetoes and a buyer that is not thinning hold in every mode. The gate is the "
                           "pre-registered rule."},
    "flow_entry_min": {"label": "Entry needs a score of at most minus",
                       "help": "Read when the entry reads the flow score: a short enters on sellers."},
    "flush_exit": {"label": "On a burst of buying while in",
                   "choices": (("off", "nothing (the pre-registered exits)"),
                               ("tighten", "lower the buy stop over the price"),
                               ("exit", "cover at the ask")),
                   "help": "The scoring exit follows it while this template is in play (the bot trades shorts "
                           "from step 5)."},
    "flush_hold_sec": {"label": "A burst counts from", "help": "Green right after the entry is often its own noise."},
    "flush_trail_r": {"unit": "R over the price", "help": "The buy stop moves down to this far over the price at the "
                                                          "burst -- never up."},
    "flush_min_r": {"help": "On: a burst counts only while the short is up this much. Off: any time."},
})


def _short_grade() -> tuple[ParamSpec, ...]:
    return (
        _p("pillar_min_run_pct", GRADE_SHORT, "Ran at least", NUMBER, SHORT_PILLAR_MIN_RUN_PCT, unit="% today",
           min=0, max=10000, step=1, help="The high of day over the prior close."),
        _p("pillar_min_fade_pct", GRADE_SHORT, "Faded at least", NUMBER, SHORT_PILLAR_MIN_FADE_PCT,
           unit="% off the high", min=0, max=100, step=0.5, help="The price when it arms, under the high of day."),
        _p("pillar_borrow_mult", GRADE_SHORT, "Borrow at least", NUMBER, SHORT_PILLAR_BORROW_MULT, unit="x the order",
           min=1, max=1000, step=1, help="IBKR's shortable estimate (tick 236) against the sleeve's size for this "
                                         "setup's risk."),
    )


def _macd_short(help_text: str, default: bool = SHORT_MACD_NEGATIVE) -> tuple[ParamSpec, ...]:
    return (
        _p("macd_negative", "setup", "MACD histogram under zero", BOOL, default, help=help_text),
        _p("macd_fast", "setup", "MACD fast", INT, SETUPS_MACD_FAST, unit="bars", min=2, max=60, step=1),
        _p("macd_slow", "setup", "MACD slow", INT, SETUPS_MACD_SLOW, unit="bars", min=3, max=120, step=1),
        _p("macd_signal", "setup", "MACD signal", INT, SETUPS_MACD_SIGNAL, unit="bars", min=2, max=60, step=1),
    )


def _ema_short(hold_help: str, tol_help: str | None = None) -> tuple[ParamSpec, ...]:
    period = _p("ema_period", "setup", "Under the EMA", INT, SETUPS_EMA_PERIOD, unit="bars", min=2, max=100, step=1,
                help=hold_help)
    if tol_help is None:
        return (period,)
    return (period, _p("ema_tol", "setup", "EMA slack", NUMBER, _pct(SETUPS_EMA_TOLERANCE), unit="%", min=0, max=10,
                       step=0.1, help=tol_help))


def _window(cutoff: str, start_help: str, cutoff_help: str) -> tuple[ParamSpec, ...]:
    return (
        _p("session_start", "entry", "Arms from", TIME, SHORT_WINDOW_START_ET, unit="ET", min="09:35", max="15:50",
           help=start_help),
        _p("entry_cutoff", "entry", "Arms until", TIME, cutoff, unit="ET", min="09:35", max="15:50", help=cutoff_help),
    )


def _risk_short(stop_help: str) -> tuple[ParamSpec, ...]:
    from constants_setups import SETUPS_MIN_STOP_DOLLARS, SETUPS_RISK_SLIPPAGE_DOLLARS, SETUPS_STOP_CAP_DOLLARS

    return (
        _p("stop_cap", "risk", "Largest risk a share", NUMBER, SETUPS_STOP_CAP_DOLLARS, unit="$", min=0.01, max=10,
           step=0.01, help=stop_help),
        _p("min_stop", "risk", "Smallest risk a share", NUMBER, SETUPS_MIN_STOP_DOLLARS, unit="$", min=0, max=5,
           step=0.01, help="A smaller risk skips the setup: the buy stop would sit in the spread."),
        _p("risk_slippage", "risk", "Slippage counted in the risk", NUMBER, SETUPS_RISK_SLIPPAGE_DOLLARS, unit="$",
           min=0, max=1, step=0.01, help="Added to the risk before the two checks above."),
    )


_TARGET_R_SHORT = dataclasses.replace(_TARGET_R, help="Target 1 at R x the risk under the entry: cover at 2R.")
_BAILOUT_SHORT = dataclasses.replace(_BAILOUT, help="Scoring exit: this many candles without a close under the "
                                                    "entry -> covered at the close.")
_SSR_CHOICE = _p("ssr", "stock", "Under SSR", CHOICE, SETUPS_SSR_TRADE,
                 choices=((SETUPS_SSR_TRADE, "trade it (the read-out reports SSR trades apart)"),
                          (SETUPS_SSR_SKIP, "skip it: a setup armed while SSR is on or unknown is filtered")),
                 help="Under SSR a short sells only above the bid: minute bars cannot say whether a breakdown "
                      "could fill. The read-out reports SSR trades as their own group, so a losing group can be "
                      "switched off here.")
_OFFSETS = (
    _p("entry_offset", "entry", "Short under the trigger by", NUMBER, SHORT_ENTRY_OFFSET_DOLLARS, unit="$", min=0,
       max=1, step=0.01, help="The entry is the trigger low minus this."),
    _p("stop_offset", "risk", "Buy stop over the pattern by", NUMBER, SHORT_STOP_OFFSET_DOLLARS, unit="$", min=0,
       max=1, step=0.01, help="The buy stop sits this far over the pattern's high."),
)


def _tail(cutoff: str) -> tuple[ParamSpec, ...]:
    """The tape, flow, grade and bot groups every short shares, its bot window its arming window (ADR 049)."""
    return _TAPE_SHORT + _FLOW_SHORT + _short_grade() + _bot_short(cutoff)


def _bot_short(cutoff: str) -> tuple[ParamSpec, ...]:
    """The bot's rules: its window defaults to the arming window (09:35 to the setup's cutoff)."""
    out = []
    for spec in _bot(SHORT_WINDOW_START_ET, cutoff):
        if spec.key == "bot_window_start":
            spec = dataclasses.replace(spec, default=SHORT_WINDOW_START_ET)
        elif spec.key == "bot_window_end":
            spec = dataclasses.replace(spec, default=cutoff)
        elif spec.key == "bot_grades":
            spec = dataclasses.replace(spec, label="Grades Nova shorts", help="Nova shorts this setup only at these "
                                                                              "grades. C is never a trade.")
        out.append(spec)
    return tuple(out)


# -- Backside lower high (ADR 049 section 5). -------------------------------------------------
_BACKSIDE: tuple[ParamSpec, ...] = _STOCK_SHORT + (_SSR_CHOICE,) + (
    _p("fade_pct", "setup", "Fade at least", NUMBER, _pct(SHORT_BACKSIDE_FADE_PCT), unit="% off the high", min=1,
       max=90, step=0.5, help="The fade's low is at least this far under the high of day."),
    _p("fade_lookback", "setup", "New low over", INT, SHORT_BACKSIDE_FADE_LOOKBACK, unit="bars", min=5, max=240,
       step=1, help="The fade's low is the lowest low of this many bars before it."),
    _p("min_bounce_bars", "setup", "Bounce at least", INT, SHORT_BACKSIDE_MIN_BOUNCE_BARS, unit="bars", min=1, max=10,
       step=1, help="Fewest candles after the fade's low."),
    _p("max_bounce_bars", "setup", "Bounce at most", INT, SHORT_BACKSIDE_MAX_BOUNCE_BARS, unit="bars", min=1, max=10,
       step=1, help="Most candles after the fade's low before the bounce ran too long."),
    _p("max_retrace", "setup", "Takes back less than", NUMBER, _pct(SHORT_BACKSIDE_MAX_RETRACE), unit="% of the fade",
       min=5, max=100, step=5, help="The bounce's high takes back less than this share of the fade."),
) + _ema_short("Every bounce candle closes at or under this EMA.", "A bounce close may sit this far over the EMA.") + (
    _macd_short("The last bounce candle's MACD histogram is under zero (the back side of the move).") + (
        _p("max_per_symbol_day", "setup", "Setups a symbol a day", INT, SHORT_MAX_PER_SYMBOL_DAY, unit="setups", min=1,
           max=10, step=1, help="The setup, then its second -- no more on one symbol that day."),
    )
) + _OFFSETS[:1] + _window(SHORT_BACKSIDE_CUTOFF_ET, "No setup arms before this time (shorts start at 09:35).",
                           "No setup arms, and none triggers, at or after this time.") + _near() + _risk_short(
    "The buy stop minus the entry. A bigger risk skips the setup.") + _OFFSETS[1:] + (
    _TARGET_R_SHORT, _BAILOUT_SHORT) + _tail(SHORT_BACKSIDE_CUTOFF_ET)

# -- Bear flag (ADR 049 section 6). -------------------------------------------------------------
_BEAR_FLAG: tuple[ParamSpec, ...] = _STOCK_SHORT + (_SSR_CHOICE,) + (
    _p("pole_min_bars", "setup", "Pole at least", INT, SHORT_BF_POLE_MIN_BARS, unit="red candles", min=1, max=20,
       step=1, help="Consecutive red candles (close under open) ending at the pole bottom."),
    _p("pole_min_pct", "setup", "Pole drop at least", NUMBER, _pct(SHORT_BF_POLE_MIN_PCT), unit="%", min=0.5, max=90,
       step=0.5, help="From the pole's highest high to its lowest low, over the high."),
    _p("pole_volume_rising", "setup", "Pole volume rising", BOOL, SHORT_BF_POLE_VOLUME_RISING,
       help="The last pole candle trades at least the first's volume (a tiring drop is skipped)."),
    _p("min_flag_bars", "setup", "Flag at least", INT, SHORT_BF_MIN_FLAG_BARS, unit="candles", min=1, max=10, step=1,
       help="Green (or doji) candles after the pole bottom."),
    _p("max_flag_bars", "setup", "Flag at most", INT, SHORT_BF_MAX_FLAG_BARS, unit="candles", min=1, max=10, step=1,
       help="More green candles than this is too much buying: the setup fails."),
    _p("max_retrace", "setup", "Flag takes back at most", NUMBER, _pct(SHORT_BF_MAX_RETRACE), unit="% of the pole",
       min=5, max=100, step=5, help="The flag's high takes back no more than this share of the pole."),
    _p("flag_volume_lighter", "setup", "Flag on lighter volume", BOOL, SHORT_BF_FLAG_VOLUME_LIGHTER,
       help="The flag's average volume is under the pole's."),
) + _ema_short("Every flag candle closes at or under this EMA (when the switch below is on).",
               "A flag close may sit this far over the EMA.") + (
    _p("ema_hold", "setup", "Flag closes stay under the EMA", BOOL, SHORT_BF_EMA_HOLD,
       help="Off: a flag close over the EMA does not fail the setup."),
    _p("reject_green_volume_high", "setup", "Skip when the biggest-volume candle is green", BOOL,
       SHORT_BF_REJECT_GREEN_VOLUME_HIGH, help="The day's highest-volume candle so far being green means buyers own "
                                               "the day (the bull flag's rule, mirrored)."),
    _p("max_pole_wick", "setup", "Pole bottom's lower wick at most", NUMBER, _pct(SHORT_BF_MAX_POLE_WICK),
       unit="% of its range", min=5, max=100, step=5, nullable=True,
       help="A big lower tail on the pole's last candle is buyers stepping in. Off: no wick check."),
) + _macd_short("The last flag candle's MACD histogram is under zero (the back side of the move).") + (
    _p("max_per_symbol_day", "setup", "Flags a symbol a day", INT, SHORT_MAX_PER_SYMBOL_DAY, unit="setups", min=1,
       max=10, step=1, help="The first and the second flag."),
) + _OFFSETS[:1] + _window(SHORT_BEAR_FLAG_CUTOFF_ET, "No flag arms before this time (shorts start at 09:35).",
                           "No flag arms, and none triggers, at or after this time.") + _near() + _risk_short(
    "The buy stop minus the entry. A bigger risk skips the setup.") + _OFFSETS[1:] + (
    _TARGET_R_SHORT, _BAILOUT_SHORT) + _tail(SHORT_BEAR_FLAG_CUTOFF_ET)

# -- Failed breakout (ADR 049 section 7). ---------------------------------------------------------
_FAILED_BREAKOUT: tuple[ParamSpec, ...] = _STOCK_SHORT + (_SSR_CHOICE,) + (
    _p("touch_pct", "setup", "A touch is within", NUMBER, _pct(SHORT_FB_TOUCH_PCT), unit="% under the high", min=0,
       max=5, step=0.1, help="A high this close under the flat top touched it (or the dollars below, whichever is "
                             "more)."),
    _p("touch_dollars", "setup", "... or within", NUMBER, SHORT_FB_TOUCH_DOLLARS, unit="$", min=0, max=1, step=0.01),
    _p("min_touches", "setup", "Touches at least", INT, SHORT_FB_MIN_TOUCHES, unit="candles", min=1, max=10, step=1,
       help="Candles that reached the flat top, the first included; one after the first made no new high."),
    _p("lookback", "setup", "Touches within", INT, SHORT_FB_LOOKBACK, unit="candles before the poke", min=2, max=240,
       step=1, help="How far back a touch counts."),
    _p("poke_dollars", "setup", "Poke at least", NUMBER, SHORT_FB_POKE_DOLLARS, unit="$ over the flat top", min=0.01,
       max=1, step=0.01, help="The poke's high is at least this over the flat top."),
    _p("fail_bars", "setup", "Fails back under within", INT, SHORT_FB_FAIL_BARS, unit="candles after the poke",
       min=0, max=10, step=1, help="The poke, or one of this many candles after it, closes back under the flat top. "
                                   "When they all close over it, the breakout held."),
    _p("trigger_bars", "setup", "Breaks down within", INT, SHORT_FB_TRIGGER_BARS, unit="candles", min=1, max=30,
       step=1, help="The trigger prints within this many candles after the failure candle, or the setup fails."),
) + _ema_short("The scoring exit's EMA (the failed breakout reads no EMA to arm).") + _macd_short(
    "On: the failure candle's MACD histogram is under zero. Off (the pre-registered rule): the failure is the turn.",
    SHORT_FB_MACD_NEGATIVE) + (
    _p("max_per_symbol_day", "setup", "Setups a symbol a day", INT, SHORT_MAX_PER_SYMBOL_DAY, unit="setups", min=1,
       max=10, step=1, help="Failed breakouts that may trigger on one symbol in a day."),
) + _OFFSETS[:1] + _window(SHORT_FAILED_BREAKOUT_CUTOFF_ET, "No setup arms before this time (shorts start at 09:35).",
                           "No setup arms, and none triggers, at or after this time.") + _near() + _risk_short(
    "The buy stop minus the entry. A bigger risk skips the setup.") + _OFFSETS[1:] + (
    _TARGET_R_SHORT, _BAILOUT_SHORT) + _tail(SHORT_FAILED_BREAKOUT_CUTOFF_ET)

# -- Lost VWAP (ADR 049 section 8). ---------------------------------------------------------------
_LOST_VWAP: tuple[ParamSpec, ...] = _STOCK_SHORT + (_SSR_CHOICE,) + (
    _p("open_at", "setup", "Over VWAP from", TIME, SHORT_LOST_VWAP_OPEN_ET, unit="ET", min="04:00", max="16:00",
       help="Every close from the first candle at or after this time up to the loss is at or over VWAP."),
    _p("retest_pct", "setup", "A retest reaches within", NUMBER, _pct(SHORT_LV_RETEST_PCT), unit="% under VWAP", min=0,
       max=5, step=0.05, help="A candle whose high reaches this close under VWAP (or over it) and closes under it "
                              "retested VWAP (or the dollars below, whichever is more)."),
    _p("retest_dollars", "setup", "... or within", NUMBER, SHORT_LV_RETEST_DOLLARS, unit="$", min=0, max=1, step=0.01),
) + _ema_short("The scoring exit's EMA (lost VWAP reads no EMA to arm).") + _macd_short(
    "On: the retest candle's MACD histogram is under zero. Off (the pre-registered rule): VWAP is the turn.",
    SHORT_LV_MACD_NEGATIVE) + _OFFSETS[:1] + _window(
    SHORT_LOST_VWAP_CUTOFF_ET, "No retest is the try before this time (shorts start at 09:35).",
    "Nothing arms, and nothing triggers, at or after this time. One try a day.") + _near() + _risk_short(
    "The buy stop (over the higher of VWAP and the retest's high) minus the entry. A bigger risk spends the day's "
    "try.") + _OFFSETS[1:] + (_TARGET_R_SHORT, _BAILOUT_SHORT) + _tail(SHORT_LOST_VWAP_CUTOFF_ET)

# -- SSR bounce short (ADR 049 section 9). ---------------------------------------------------------
_SSR_BOUNCE: tuple[ParamSpec, ...] = _STOCK_SHORT + (
    _p("drop_pct", "setup", "Drop at least", NUMBER, _pct(SHORT_SSR_DROP_PCT), unit="% to a new low", min=1, max=90,
       step=0.5, help="The new low of day is at least this far under the highest high of the candles before it."),
    _p("drop_lookback", "setup", "Drop measured over", INT, SHORT_SSR_DROP_LOOKBACK, unit="bars", min=2, max=240,
       step=1),
    _p("bounce_greens", "setup", "Bounce of", INT, SHORT_SSR_BOUNCE_GREENS, unit="green candles", min=1, max=10, step=1,
       help="The candles right after the low are green."),
    _p("arm_pct", "setup", "Rests within", NUMBER, _pct(SHORT_SSR_ARM_PCT), unit="% under the level", min=0.1, max=20,
       step=0.1, help="When the bounce comes this close under the level, the short rests one cent under it."),
    _p("round_step", "setup", "Round numbers every", NUMBER, SHORT_SSR_ROUND_STEP, unit="$", min=0.05, max=10,
       step=0.05, help="The half or whole dollar the level may be."),
    _p("cancel_min", "setup", "Cancelled after", INT, SHORT_SSR_CANCEL_MIN, unit="minutes", min=1, max=120, step=1,
       help="A resting short no buyer lifted in this long is cancelled."),
) + _ema_short("The scoring exit's EMA (the SSR bounce reads no EMA to arm).") + (
    _p("max_per_symbol_day", "setup", "Setups a symbol a day", INT, SHORT_MAX_PER_SYMBOL_DAY, unit="setups", min=1,
       max=10, step=1, help="Resting shorts that may fill on one symbol in a day."),
    _p("entry_offset", "entry", "Rests under the level by", NUMBER, SHORT_ENTRY_OFFSET_DOLLARS, unit="$", min=0, max=1,
       step=0.01, help="The resting short's price is the level minus this: buyers pushing into the level fill it, "
                       "above the bid."),
) + _window(SHORT_SSR_BOUNCE_CUTOFF_ET, "No short rests before this time (shorts start at 09:35).",
            "Nothing arms, and nothing fills, at or after this time.") + _near() + (
    _p("stop_pct", "risk", "Buy stop over the entry", NUMBER, _pct(SHORT_SSR_STOP_PCT), unit="%", min=0.1, max=50,
       step=0.1, help="The buy stop sits this far over the entry, or the dollars below, whichever is more."),
    _p("stop_min", "risk", "... at least", NUMBER, SHORT_SSR_STOP_MIN_DOLLARS, unit="$", min=0.01, max=5, step=0.01),
) + _risk_short("The buy stop minus the entry. A bigger risk skips the setup.") + (
    _TARGET_R_SHORT, _BAILOUT_SHORT) + _tail(SHORT_SSR_BOUNCE_CUTOFF_ET)

SHORT_CATALOGUE: dict[str, tuple[ParamSpec, ...]] = {
    BOT_SETUP_BACKSIDE: _BACKSIDE,
    BOT_SETUP_BEAR_FLAG: _BEAR_FLAG,
    BOT_SETUP_FAILED_BREAKOUT: _FAILED_BREAKOUT,
    BOT_SETUP_LOST_VWAP: _LOST_VWAP,
    BOT_SETUP_SSR_BOUNCE: _SSR_BOUNCE,
}

_PRE = "Pre-registered in ADR 049 before any code read a bar; its read-out and its five-year test are its first tests. "
SHORT_SOURCES: dict[str, str] = {
    BOT_SETUP_BACKSIDE: _PRE + "The first pullback mirrored: a fade off the high of day, a 1-3 candle bounce that stays "
                               "under it, the short under the bounce's low. It arms 09:35-11:30.",
    BOT_SETUP_BEAR_FLAG: _PRE + "The bull flag mirrored: a pole of red candles, a 2-3 candle flag drifting up, the short "
                                "under the flag's low. It arms 09:35-15:30.",
    BOT_SETUP_FAILED_BREAKOUT: _PRE + "The flat-top breakout mirrored: a tested flat top, a poke over it, a close back "
                                      "under it, the short under that candle. It arms 09:35-11:30.",
    BOT_SETUP_LOST_VWAP: _PRE + "Red to green mirrored: over VWAP from the open, a close under it, a retest VWAP turns "
                                "back, the short under the retest. One try a day, 09:35-12:00.",
    BOT_SETUP_SSR_BOUNCE: _PRE + "SSR stocks only: after a drop to a new low, the short rests one cent under the "
                                 "nearest level over the bounce, so buyers fill it above the bid. 09:35-15:50.",
}

SHORT_GROUP_LABELS: dict[str, tuple[str, str]] = {
    GRADE_SHORT: ("Short grade", "Grades every armed short A / B / C on five pillars: ran, faded, under VWAP, bad "
                                 "news or dilution on file, and borrow. A pillar Nova does not know never passes."),
}
