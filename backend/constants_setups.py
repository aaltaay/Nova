"""Setup scanner + tape gate tunables (ADR 022, Bot-Trading-Plan section 2g).

Owner: backend/setup_scanner/. Re-exported from the constants barrel.

The pullback numbers are the pre-registered P1 rules the research screen used
(research/momentum/backtest_setups.py), so the live scanner and the backtest
agree bar for bar. Numbers marked CHOSEN were left open by the source material
and are ours; the scoreboard exists to tell us whether they are right.
"""
from __future__ import annotations

from constants_bot import (
    BOT_SETUP_BULL_FLAG,
    BOT_SETUP_FIRST_PULLBACK,
    BOT_SETUP_FLAT_TOP,
    BOT_SETUP_RED_TO_GREEN,
)

# The board / socket payload. 2 (ADR 031): rows and proposals carry
# ``setup_type``, and ``setups[]`` summarizes each setup with a scanner.
SETUPS_SCHEMA_VERSION = 2
# setups.db: 2 adds template_id / template_rev / params_hash (ADR 029); a v1
# file is migrated in place, its rows becoming the default template's. 3 (ADR
# 031) adds setup_type and detail; a v2 file's rows are the first pullback's.
SETUPS_DB_SCHEMA_VERSION = 3

# -- Session window (America/New_York). The material's window is 07:00-10:00;
# the research screen ran 09:30-11:30. Covering 07:00-11:30 lets the
# scoreboard split pre-market from regular hours instead of guessing. CHOSEN.
SETUPS_SESSION_START_ET = "07:00"
SETUPS_ENTRY_CUTOFF_ET = "11:30"
SETUPS_SCORE_FLAT_BY_ET = "15:55"       # scoring stops here, as in the backtest
SETUPS_BAR_SEC = 60                     # one-minute bars

# -- Pullback family (P1). Same values as the research harness Params.
SETUPS_LEG_PCT = 0.05                   # leg high >= 5% over the lowest low of the window
SETUPS_LEG_WINDOW_BARS = 10
SETUPS_LEG_LOOKBACK_BARS = 30           # leg high is the highest of the prior 30 bars
SETUPS_REQUIRE_HOD = True               # ... and the day's high so far (pre-market included)
SETUPS_MIN_PULLBACK_BARS = 1
SETUPS_MAX_PULLBACK_BARS = 3
SETUPS_MAX_RETRACE = 0.5                # pullback gives back less than half the leg
SETUPS_EMA_PERIOD = 9
SETUPS_EMA_TOLERANCE = 0.0              # pullback closes may sit this fraction under the 9 EMA
SETUPS_MACD_FAST = 12
SETUPS_MACD_SLOW = 26
SETUPS_MACD_SIGNAL = 9
SETUPS_MACD_POSITIVE = True             # prior bar's MACD histogram > 0 to arm
SETUPS_STOP_CAP_DOLLARS = 0.20          # skip a setup whose risk is larger
SETUPS_MIN_STOP_DOLLARS = 0.03          # ... or smaller than this
SETUPS_ENTRY_OFFSET_DOLLARS = 0.01      # buy one cent over the last pullback bar's high
SETUPS_RISK_SLIPPAGE_DOLLARS = 0.01     # the risk caps are checked with one cent of slippage, as the research did
SETUPS_TARGET_R = 2.0                   # target 1 = max(leg high, entry + 2R)
SETUPS_TARGET_MODE = "leg_or_r"         # ADR 029: "fixed" makes target 1 entry + SETUPS_TARGET_FIXED_DOLLARS
SETUPS_TARGET_FIXED_DOLLARS = 0.20      # the material's 20c target, for a template that asks for it
SETUPS_BAILOUT_BARS = 5                 # scoring: 5 bars without a close above entry -> out
SETUPS_MAX_PER_SYMBOL_DAY = 2           # first and second pullback

# -- Bull flag (ADR 031): pre-registered from the operator's material, never tested
# on bars. The material's rules: 3+ green candles, then 2-3 red candles none of which
# breaks the high of the candle before it, a flag giving back no more than half the
# pole on lighter volume, and the entry "the first candle to make a new high". The
# numbers the material leaves open are CHOSEN, the first pullback's where it has one.
SETUPS_BF_POLE_MIN_BARS = 3             # consecutive green candles (close over open)
SETUPS_BF_POLE_MIN_PCT = 0.05           # the pole's rise, lowest low to highest high ... CHOSEN
SETUPS_BF_POLE_MIN_DOLLARS = 0.30       # ... or at least this many dollars. CHOSEN
SETUPS_BF_POLE_VOLUME_RISING = True     # the last pole candle's volume >= the first's
SETUPS_BF_MIN_FLAG_BARS = 2             # one candle is a micro pullback, not a flag
SETUPS_BF_MAX_FLAG_BARS = 3             # "more than three candles ... too much selling"
SETUPS_BF_MAX_RETRACE = 0.5             # the flag low gives back no more than half the pole
SETUPS_BF_FLAG_VOLUME_LIGHTER = True    # the flag's average volume under the pole's
SETUPS_BF_EMA_HOLD = True               # every flag close at or above the EMA
SETUPS_BF_EMA_TOUCH_PCT = None          # off: the flag low within this fraction of the EMA
SETUPS_BF_REJECT_RED_VOLUME_HIGH = True  # the day's highest-volume candle is red -> no setup
SETUPS_BF_MAX_POLE_WICK = 0.40          # the pole-top candle's upper wick over its range. CHOSEN
SETUPS_BF_REQUIRE_HOD = False           # the material asks no new high of day
SETUPS_BF_MAX_PER_SYMBOL_DAY = 2        # the first and second flag, skip the third
SETUPS_BF_TARGET_MODES = ("leg_or_r", "leg", "fixed")

# -- Flat-top breakout (P2, research/momentum/backtest_setups.py find_flat_top).
SETUPS_FT_IMPULSE_PCT = 0.03            # the move into the high of day over the window's lowest low
SETUPS_FT_LEG_WINDOW_BARS = 10
SETUPS_FT_MIN_CONSOL = 2                # base candles right after the high-of-day candle
SETUPS_FT_MAX_CONSOL = 6
SETUPS_FT_BAND = 0.02                   # every base close within this fraction under the high
SETUPS_FT_ENTRY_HOLD = "hold"           # the taught way: a green candle holding over the high
SETUPS_FT_ENTRY_BREAK = "break"         # the variant: the break itself
SETUPS_FT_ENTRY = SETUPS_FT_ENTRY_HOLD
SETUPS_FT_HOLD_BARS = 3                 # the hold must come within this many candles after the break
SETUPS_FT_MAX_PER_SYMBOL_DAY = 2
SETUPS_FT_TARGET_MODES = ("r", "fixed")

# -- Red to green (P3, find_red_to_green): the open, then back through it.
SETUPS_R2G_OPEN_ET = "09:30"            # the level is the open of the first candle at or after this
SETUPS_R2G_CUTOFF_ET = "10:30"          # reclaim by
SETUPS_R2G_MIN_RED_BARS = 1             # closes under the open, counted from the opening candle
SETUPS_R2G_TARGET_HOD = True            # target 1 is at least the high of day

# -- "Near": price this close to the trigger is the moment to read the tape. CHOSEN.
SETUPS_NEAR_DOLLARS = 0.03
SETUPS_NEAR_PCT = 0.003

# -- Grade from the Five Pillars at arm time (standard tier).
SETUPS_PILLAR_MIN_PRICE = 2.0
SETUPS_PILLAR_MAX_PRICE = 20.0
SETUPS_PILLAR_MIN_CHANGE_PCT = 10.0
SETUPS_PILLAR_MIN_RVOL = 5.0
SETUPS_PILLAR_MAX_FLOAT = 20_000_000
SETUPS_GRADE_A = "A"                    # all five known and passing
SETUPS_GRADE_B = "B"                    # four passing
SETUPS_GRADE_C = "C"                    # three or fewer, or unknown data

# -- Tape gate (live Level 2 + time and sales at the trigger).
TAPE_GATE_WINDOW_SEC = 10.0             # prints and book history looked at. CHOSEN
TAPE_GATE_STALE_BOOK_SEC = 3.0          # no book newer than this -> blind
TAPE_GATE_SPREAD_MAX_DOLLARS = 0.05     # veto a spread wider than max(5c, 1% of price). CHOSEN
TAPE_GATE_SPREAD_MAX_PCT = 0.01
TAPE_GATE_BAND_DOLLARS = 0.05           # ask levels from trigger-1c to trigger+5c are "at the level"
TAPE_GATE_BIG_SELLER_SHARES = 100_000   # a displayed seller this big at the level vetoes (material)
TAPE_GATE_WALL_SHARES = 25_000          # a seller this big makes us wait until it thins (material)
TAPE_GATE_THIN_FRACTION = 0.5           # the wall shrank by half inside the window -> thinning. CHOSEN
TAPE_GATE_MIN_ASK_PRINTS = 3            # "green on the tape": at least this many prints at the ask. CHOSEN
TAPE_GATE_HIDDEN_SELLER_MULT = 2.0      # ask-side volume >= 2x the inside ask with no uptick -> hidden seller. CHOSEN
TAPE_GATE_RED_BURST_MULT = 2.0          # bid-side volume > 2x ask-side volume -> red burst, wait. CHOSEN
TAPE_GATE_BOOK_SAMPLE_SEC = 0.5         # engine samples the held book this often

TAPE_VERDICT_GO = "go"
TAPE_VERDICT_WAIT = "wait"
TAPE_VERDICT_VETO = "veto"
TAPE_VERDICT_BLIND = "blind"
TAPE_VERDICTS = (TAPE_VERDICT_GO, TAPE_VERDICT_WAIT, TAPE_VERDICT_VETO, TAPE_VERDICT_BLIND)

# -- Tape flow (ADR 034): one score for who is winning the tape, -1 (sellers) to +1 (buyers).
# Every number is CHOSEN and tuned per template; eyes/flow_study.py measures what the score says.
TAPE_FLOW_WINDOW_SEC = 10.0             # the readings look at this many seconds
TAPE_FLOW_BASELINE_SEC = 120.0          # the tape's usual pace is measured over this, before the window
TAPE_FLOW_MIN_PRINTS = 5                # fewer lit prints at the bid or the ask than this reads quiet
TAPE_FLOW_MIN_SHARES = 1_000            # ... or fewer shares than this
TAPE_FLOW_PACE_FULL = 3.0               # the window's pace at this multiple of the baseline reads full strength
TAPE_FLOW_DRIFT_FULL = 0.005            # a move of this fraction of price inside the window reads full strength
TAPE_FLOW_BOOK_LEVELS = 5               # displayed prices a side the book reading sums
TAPE_FLOW_W_IMBALANCE = 5.0             # weights of the four readings in the score's mean
TAPE_FLOW_W_PACE = 2.0
TAPE_FLOW_W_DRIFT = 2.0
TAPE_FLOW_W_BOOK = 1.0
TAPE_FLOW_BURST_AT = 0.5                # a score at or over this is a burst
TAPE_FLOW_FLUSH_AT = 0.5                # a score at or under minus this is a flush
TAPE_FLOW_EVAL_SEC = 1.0                # a trade on is read this often after its trigger
TAPE_FLOW_READING_STALE_SEC = 5.0       # the bot ignores a reading older than this
TAPE_FLOW_BURST = "burst"
TAPE_FLOW_FLUSH = "flush"
TAPE_FLOW_NEUTRAL = "neutral"
TAPE_FLOW_QUIET = "quiet"               # too little tape to say
TAPE_FLOW_BLIND = "blind"               # no prints and no book: Nova holds no line
TAPE_FLOW_LABELS = (TAPE_FLOW_BURST, TAPE_FLOW_FLUSH, TAPE_FLOW_NEUTRAL, TAPE_FLOW_QUIET, TAPE_FLOW_BLIND)

# How the tape decides an entry (a template's ``tape_entry``). ``gate`` is the pre-registered rule.
TAPE_ENTRY_GATE = "gate"                # green prints at the ask and no red burst (ADR 022)
TAPE_ENTRY_SCORE = "score"              # the flow score at or over the minimum instead of the print counts
TAPE_ENTRY_BOTH = "both"                # the gate's green and the score
TAPE_ENTRY_MODES = (TAPE_ENTRY_GATE, TAPE_ENTRY_SCORE, TAPE_ENTRY_BOTH)
TAPE_ENTRY_MIN_SCORE = 0.3

# What a flush does to a trade on (a template's ``flush_exit``). Off is the pre-registered rule.
FLUSH_EXIT_OFF = "off"
FLUSH_EXIT_TIGHTEN = "tighten"          # the stop moves up to ``flush_trail_r`` R under the price
FLUSH_EXIT_EXIT = "exit"                # out at the bid
FLUSH_EXIT_MODES = (FLUSH_EXIT_OFF, FLUSH_EXIT_TIGHTEN, FLUSH_EXIT_EXIT)
FLUSH_EXIT_HOLD_SEC = 10.0              # a flush this soon after the entry is the entry's own noise
FLUSH_EXIT_TRAIL_R = 0.5
FLUSH_EXIT_MIN_R = None                 # on: a flush counts only while the trade is up at least this many R

# -- States (one vocabulary for the board, the scoreboard and the UI).
SETUP_STATE_WATCHING = "watching"
SETUP_STATE_LEG = "leg"
SETUP_STATE_PULLBACK = "pullback"       # pulling back but not armable yet (MACD, risk)
SETUP_STATE_ARMED = "armed"
SETUP_STATE_NEAR = "near"
SETUP_STATE_TRIGGERED = "triggered"
SETUP_STATE_FAILED = "failed"
SETUP_STATES = (
    SETUP_STATE_WATCHING, SETUP_STATE_LEG, SETUP_STATE_PULLBACK, SETUP_STATE_ARMED,
    SETUP_STATE_NEAR, SETUP_STATE_TRIGGERED, SETUP_STATE_FAILED,
)
SETUP_KIND_FIRST_PULLBACK = "first_pullback"
SETUP_KIND_SECOND_PULLBACK = "second_pullback"
# ADR 031: the kind without "second_" is the first of that setup on that symbol that day.
SETUP_KIND_BULL_FLAG = "bull_flag"
SETUP_KIND_SECOND_BULL_FLAG = "second_bull_flag"
SETUP_KIND_FLAT_TOP = "flat_top_breakout"
SETUP_KIND_SECOND_FLAT_TOP = "second_flat_top_breakout"
SETUP_KIND_RED_TO_GREEN = "red_to_green"
# The read-out counts each setup's first-of-the-day kind (ADR 027, ADR 031).
SETUPS_READOUT_KINDS = {
    BOT_SETUP_FIRST_PULLBACK: SETUP_KIND_FIRST_PULLBACK,
    BOT_SETUP_BULL_FLAG: SETUP_KIND_BULL_FLAG,
    BOT_SETUP_FLAT_TOP: SETUP_KIND_FLAT_TOP,
    BOT_SETUP_RED_TO_GREEN: SETUP_KIND_RED_TO_GREEN,
}

# -- The pre-registered read-out (Bot-Trading-Plan §2g, ADR 027): read once
# READOUT_MIN_GO triggered first-pullback setups had the tape at go at the
# trigger; they pass when their average net R is above READOUT_MIN_NET_R and
# above the blind / wait average. No pass by READOUT_FAIL_GO -> failed.
SETUPS_READOUT_KIND = SETUP_KIND_FIRST_PULLBACK
SETUPS_READOUT_MIN_GO = 50
SETUPS_READOUT_FAIL_GO = 100
SETUPS_READOUT_MIN_NET_R = 0.2
SETUPS_READOUT_CACHE_SEC = 30.0
SETUPS_READOUT_COLLECTING = "collecting"
SETUPS_READOUT_PASSED = "passed"
SETUPS_READOUT_NOT_PASSED = "not_passed"
SETUPS_READOUT_FAILED = "failed"
SETUPS_READOUT_UNAVAILABLE = "unavailable"

# -- Scoreboard outcomes.
SETUP_OUTCOME_TARGET_FIRST = "target_first"
SETUP_OUTCOME_STOP_FIRST = "stop_first"
SETUP_OUTCOME_OPEN = "open"             # neither touched yet
SETUP_OUTCOME_NOT_TRIGGERED = "not_triggered"
SETUPS_SCORE_WINDOW_MIN = 15            # MFE / MAE measured over this many minutes after trigger
SETUPS_DB_FILENAME = "setups.db"        # under paths.cache_dir(), not git-tracked
SETUPS_BOARD_MAX_ROWS = 40              # per setup (ADR 031)
SETUPS_BOARD_PUSH_SEC = 1.0             # socket push cadence

# -- Templates (ADR 029): named variations of each setup's parameters. The
# built-in default is the pre-registered rules above; the operator's own live
# in the operator cache. Every template of every setup with a scanner is watched at
# once, one lane each (the per-setup cap bounds the lanes); only each setup's template
# in play proposes (ADR 031).
SETUP_TEMPLATES_SCHEMA_VERSION = 1
SETUP_TEMPLATES_FILENAME = "setup-templates.json"   # under paths.cache_dir(), not git-tracked
SETUP_TEMPLATE_DEFAULT_ID = "default"
SETUP_TEMPLATE_DEFAULT_NAME = "Default (pre-registered)"
# The default's rules revision. Bump it when the defaults above change what the
# scanner arms or scores, so the read-out starts over for the new rules.
SETUP_TEMPLATE_DEFAULT_REV = 1
SETUP_TEMPLATES_MAX_PER_SETUP = 6                   # the default included; all watched at once
SETUP_TEMPLATE_NAME_MAX = 40
SETUP_TEMPLATE_NOTE_MAX = 280
SETUP_TEMPLATES_POLL_SEC = 1.0                      # the engine re-reads the store this often

