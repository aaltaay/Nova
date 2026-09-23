"""Setup scanner + tape gate tunables (ADR 022, Bot-Trading-Plan section 2g).

Owner: backend/setup_scanner/. Re-exported from the constants barrel.

The pullback numbers are the pre-registered P1 rules the research screen used
(research/momentum/backtest_setups.py), so the live scanner and the backtest
agree bar for bar. Numbers marked CHOSEN were left open by the source material
and are ours; the scoreboard exists to tell us whether they are right.
"""
from __future__ import annotations

SETUPS_SCHEMA_VERSION = 1

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
SETUPS_BAILOUT_BARS = 5                 # scoring: 5 bars without a close above entry -> out
SETUPS_MAX_PER_SYMBOL_DAY = 2           # first and second pullback

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

# -- Scoreboard outcomes.
SETUP_OUTCOME_TARGET_FIRST = "target_first"
SETUP_OUTCOME_STOP_FIRST = "stop_first"
SETUP_OUTCOME_OPEN = "open"             # neither touched yet
SETUP_OUTCOME_NOT_TRIGGERED = "not_triggered"
SETUPS_SCORE_WINDOW_MIN = 15            # MFE / MAE measured over this many minutes after trigger
SETUPS_DB_FILENAME = "setups.db"        # under paths.cache_dir(), not git-tracked
SETUPS_BOARD_MAX_ROWS = 40
SETUPS_BOARD_PUSH_SEC = 1.0             # socket push cadence
