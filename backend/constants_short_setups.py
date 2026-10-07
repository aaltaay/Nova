"""The five short setups' pre-registered numbers (ADR 049; its step 4 section names the CHOSEN ones).

Owner: backend/setup_scanner/ (the detectors), backend/setup_templates/ (the defaults a template starts from),
research/shorts/ (the five-year test). Not re-exported from the constants barrel. Every number here is a
template parameter's default: a variation is a template, never an edit here (an edit is a new rules revision).
"""
from __future__ import annotations

# -- Kinds: the setup's id is the first of the day on a symbol, ``second_<id>`` the second (Lost VWAP: one try).
SETUP_KIND_BACKSIDE = "backside_lower_high"
SETUP_KIND_SECOND_BACKSIDE = "second_backside_lower_high"
SETUP_KIND_BEAR_FLAG = "bear_flag"
SETUP_KIND_SECOND_BEAR_FLAG = "second_bear_flag"
SETUP_KIND_FAILED_BREAKOUT = "failed_breakout"
SETUP_KIND_SECOND_FAILED_BREAKOUT = "second_failed_breakout"
SETUP_KIND_LOST_VWAP = "lost_vwap"
SETUP_KIND_SSR_BOUNCE = "ssr_bounce"
SETUP_KIND_SECOND_SSR_BOUNCE = "second_ssr_bounce"

# -- Windows (ADR 049): each arming window is its bot window, inside the short hours (09:35-15:50, ADR 048).
SHORT_WINDOW_START_ET = "09:35"
SHORT_BACKSIDE_CUTOFF_ET = "11:30"
SHORT_BEAR_FLAG_CUTOFF_ET = "15:30"
SHORT_FAILED_BREAKOUT_CUTOFF_ET = "11:30"
SHORT_LOST_VWAP_CUTOFF_ET = "12:00"
SHORT_SSR_BOUNCE_CUTOFF_ET = "15:50"
SHORT_LOST_VWAP_OPEN_ET = "09:30"        # "over VWAP from the open": the first candle at or after this

# -- Shared by the five.
SHORT_ENTRY_OFFSET_DOLLARS = 0.01        # short one cent under the trigger low
SHORT_STOP_OFFSET_DOLLARS = 0.01         # the buy stop one cent over the pattern's high
SHORT_MAX_PER_SYMBOL_DAY = 2             # the setup and its second; Lost VWAP one try
SHORT_MACD_NEGATIVE = True               # the last pattern candle's MACD histogram under zero (the back side)

# -- Backside lower high (mirror of the first pullback).
SHORT_BACKSIDE_FADE_PCT = 0.08           # the fade's low at least this far under the high of day
SHORT_BACKSIDE_FADE_LOOKBACK = 30        # the fade's low is the lowest low of this many candles before it
SHORT_BACKSIDE_MIN_BOUNCE_BARS = 1
SHORT_BACKSIDE_MAX_BOUNCE_BARS = 3
SHORT_BACKSIDE_MAX_RETRACE = 0.5         # the bounce takes back less than this share of the fade
SHORT_BACKSIDE_STALE_BARS = 10           # how far back a fade can still explain a "failed" row

# -- Bear flag (mirror of the bull flag).
SHORT_BF_POLE_MIN_BARS = 3               # consecutive red candles
SHORT_BF_POLE_MIN_PCT = 0.05             # the drop, pole high to pole low, over the pole high
SHORT_BF_POLE_VOLUME_RISING = True       # the last pole candle trades at least the first's volume
SHORT_BF_MIN_FLAG_BARS = 2
SHORT_BF_MAX_FLAG_BARS = 3
SHORT_BF_MAX_RETRACE = 0.5               # the flag's high takes back no more than this share of the pole
SHORT_BF_FLAG_VOLUME_LIGHTER = True
SHORT_BF_EMA_HOLD = True                 # every flag close at or under the EMA
SHORT_BF_REJECT_GREEN_VOLUME_HIGH = True  # the day's biggest-volume candle green: buyers own the day
SHORT_BF_MAX_POLE_WICK = 0.40            # the pole-bottom candle's lower wick, of its range

# -- Failed breakout (mirror of the flat-top breakout).
SHORT_FB_TOUCH_PCT = 0.005               # a touch: a high within this of the flat top, or the dollars below
SHORT_FB_TOUCH_DOLLARS = 0.01
SHORT_FB_MIN_TOUCHES = 2                 # the first touch counted
SHORT_FB_LOOKBACK = 30                   # CHOSEN (step 4): touches counted in the 30 candles before the poke
SHORT_FB_POKE_DOLLARS = 0.01             # the poke's high at least this over the flat top
SHORT_FB_FAIL_BARS = 2                   # the poke, or one of the 2 candles after it, closes back under
SHORT_FB_TRIGGER_BARS = 3                # CHOSEN (step 4): the trigger prints within 3 candles of the failure
SHORT_FB_MACD_NEGATIVE = False           # no MACD rule by default: the failure is the turn

# -- Lost VWAP (mirror of red to green).
SHORT_LV_RETEST_PCT = 0.002              # CHOSEN: a retest's high within this of VWAP, or the dollars below
SHORT_LV_RETEST_DOLLARS = 0.01
SHORT_LV_MACD_NEGATIVE = False

# -- SSR bounce short.
SHORT_SSR_DROP_PCT = 0.06                # the new low of day at least this under the high of the 30 candles before
SHORT_SSR_DROP_LOOKBACK = 30
SHORT_SSR_BOUNCE_GREENS = 2              # green candles right after the low
SHORT_SSR_ARM_PCT = 0.02                 # armed when the price comes within this under the level
SHORT_SSR_CANCEL_MIN = 10                # the resting short is cancelled this many minutes after it armed
SHORT_SSR_STOP_PCT = 0.02                # the buy stop this far over the entry ...
SHORT_SSR_STOP_MIN_DOLLARS = 0.05        # ... and at least this
SHORT_SSR_ROUND_STEP = 0.50              # the half or whole dollar over the price

# -- SSR in the scanner and the templates (ADR 049 section 11).
SETUPS_SSR_ON = "on"
SETUPS_SSR_OFF = "off"
SETUPS_SSR_UNKNOWN = "unknown"
SETUPS_SSR_TRADE = "trade"               # a breakdown template trades under SSR too (the default)
SETUPS_SSR_SKIP = "skip"                 # ... or filters a setup armed while SSR is on or unknown

# -- The short grade's thresholds (ADR 049 section 10).
SHORT_PILLAR_MIN_RUN_PCT = 30.0          # the high of day over the prior close, percent
SHORT_PILLAR_MIN_FADE_PCT = 8.0          # the price at arm under the high of day, percent
SHORT_PILLAR_BORROW_MULT = 10.0          # IBKR's shortable estimate over the order's shares

# -- The five-year test's result files (ADR 049 section 12): written by research/shorts/, read by
# setup_scanner.short_tests. No agent writes one.
SHORT_TESTS_DIR_ENV = "NOVA_SHORT_TESTS_DIR"
SHORT_TESTS_SUBDIR = ("research", "short_tests")   # under NOVA_MARKET_DATA_DIR
SHORT_TESTS_SCHEMA_VERSION = 1
SHORT_TESTS_CACHE_SEC = 30.0             # the lock re-reads a result at most this often
SHORT_TESTS_STALE_SEC = 30 * 60          # a running test with no update for this long says so
SHORT_TEST_QUEUED = "queued"
SHORT_TEST_RUNNING = "running"
SHORT_TEST_PASSED = "passed"
SHORT_TEST_FAILED = "failed"
SHORT_TEST_ERROR = "error"
SHORT_TEST_STATES = (SHORT_TEST_RUNNING, SHORT_TEST_PASSED, SHORT_TEST_FAILED, SHORT_TEST_ERROR)
# Gate 1's kill criteria, unchanged (Bot-Trading-Plan section L3).
SHORT_TEST_MIN_TRADES = 300
SHORT_TEST_SHUFFLES = 1000
SHORT_TEST_MAX_P = 0.05
SHORT_TEST_COMMAND = "py -3 research/shorts/test_shorts.py --setup {setup}"
