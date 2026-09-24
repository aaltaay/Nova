"""The bot's read on one stock (ADR 036): every number its rules and reads use.

A number that is the scanner's own (a stop cap, a target in R, a tape-gate wall) is read from the
setup's template or ``constants_setups``; these are the read's.
"""
from __future__ import annotations

STOCK_READ_SCHEMA_VERSION = 1

# -- the plan -------------------------------------------------------------------------------------
STOCK_READ_TARGET_R = 2.0                   # the operator's 2:1 -- a hand plan's target is entry + 2 x risk
STOCK_READ_MANUAL_STOP_BARS = 3             # a hand plan's stop: the lowest low of the last N closed 1-min bars
STOCK_READ_TRIGGERED_PLAN_SEC = 30 * 60     # a triggered setup stays the plan this long after its trigger
STOCK_READ_STOP_CAP_DEFAULT = 0.20          # a hand plan's cap when no lane names one (the scanners' default)

# -- the read's own rules ---------------------------------------------------------------------------
STOCK_READ_VOLUME_PROFILE_BARS = 10         # green vs red volume over the last N closed 1-min candles
STOCK_READ_MEDIAN_RANGE_BARS = 20           # a "normal candle": the median 1-min range of the last N
STOCK_READ_RVOL_OK = 5.0                    # the Five Pillars' relative-volume bar
STOCK_READ_RVOL_WARN = 2.0
STOCK_READ_FLOAT_OK = 20_000_000            # a float under this can squeeze
STOCK_READ_FLOAT_BAD = 50_000_000           # over this the float is heavy for a small-cap momentum trade
STOCK_READ_ROTATION_OK = 1.0                # today's volume at least one float
STOCK_READ_HOD_NEAR_PCT = 0.02              # within 2% under the high of day reads as at the high
STOCK_READ_HOD_FAR_PCT = 0.10               # 10% or more under it ...
STOCK_READ_HOD_STALE_MIN = 60.0             # ... with no new high for an hour reads as faded
STOCK_READ_ROUND_STEP = 0.5                 # half and whole dollars
STOCK_READ_ROUND_NEAR_PCT = 0.02            # a round number this close over the price is in the way
STOCK_READ_BORROW_HTB_FEE_PCT = 20.0        # an annual borrow fee at or over this reads hard to borrow
STOCK_READ_SI_HIGH_SHARE = 0.15             # short interest this share of the float or more reads as fuel
STOCK_READ_SPLIT_RECENT_DAYS = 90           # a reverse split this recent shrank the share count
STOCK_READ_PULL_WINDOW_SEC = 60.0           # book-watch flags this recent count as "being pulled"
STOCK_READ_PRINTS_WINDOW_SEC = 60.0         # prints per minute from the sensor tape ring
STOCK_READ_BACKSIDE_TAIL_SHARE = 0.5        # a topping tail: the upper wick is at least half the candle
STOCK_READ_BACKSIDE_LOOK_BARS = 5           # backside warnings read the last N closed candles

# -- the history ---------------------------------------------------------------------------------------
STOCK_READ_RUN_MIN_PCT = 0.40               # a run: a session whose high was 40% or more over the prior close
STOCK_READ_HISTORY_READ_DAYS = 260          # daily bars read for the runs (about a year)
STOCK_READ_HISTORY_CHART_DAYS = 120         # daily bars sent for the history chart
STOCK_READ_SETUPS_HISTORY_DAYS = 365        # armed setups on the symbol counted this far back

# -- serving -------------------------------------------------------------------------------------------
STOCK_READ_CACHE_SEC = 2.0                  # one read per (symbol, entry, stop) serves every poll inside this
STOCK_READ_BARS_LIMIT = 1000                # one 04:00-20:00 session of 1-min bars (960)
STOCK_READ_BARS_5M_LIMIT = 400              # 5-min bars read for the 5-minute MACD (two sessions and more)
STOCK_READ_DECISIONS_MAX_EVENTS = 400       # a day's timeline is cut here (oldest kept, a note says so)
STOCK_READ_AUDIT_TAIL = 2000                # bot audit lines read for one symbol's day
STOCK_READ_DECISIONS_CACHE = 16             # (date, symbol, journal size) timelines kept in memory
