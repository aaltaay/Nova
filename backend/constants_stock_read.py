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
STOCK_READ_ROUND_NEAR_PCT = 0.02            # a round number this close over the price is in the way
STOCK_READ_BORROW_HTB_FEE_PCT = 20.0        # an annual borrow fee at or over this reads hard to borrow
STOCK_READ_SI_HIGH_SHARE = 0.15             # short interest this share of the float or more reads as fuel
STOCK_READ_SPLIT_RECENT_DAYS = 90           # a reverse split this recent shrank the share count
STOCK_READ_PULL_WINDOW_SEC = 60.0           # book-watch flags this recent count as "being pulled"
STOCK_READ_PRINTS_WINDOW_SEC = 60.0         # prints per minute from the sensor tape ring
STOCK_READ_BACKSIDE_TAIL_SHARE = 0.5        # a topping tail: the upper wick is at least half the candle
STOCK_READ_BACKSIDE_LOOK_BARS = 5           # backside warnings read the last N closed candles

# -- the day's levels (ADR 036 amendment 2026-09-30) ------------------------------------------------
STOCK_READ_LEVELS_SCHEMA_VERSION = 1
STOCK_READ_LEVEL_SWING_BARS = 2             # a swing high (low): over (under) the two candles either side
STOCK_READ_LEVEL_TOUCH_PCT = 0.003          # swing highs (lows) within 0.3% of each other are one level ...
STOCK_READ_LEVEL_TOUCH_MIN = 0.01           # ... and a cent is always the same level
STOCK_READ_LEVEL_MIN_TOUCHES = 2            # a level is a double top (bottom) or more
STOCK_READ_LEVEL_MERGE_PCT = 0.006          # today's levels within 0.6% are one zone ...
STOCK_READ_LEVEL_MERGE_MIN = 0.02           # ... and within 2 cents always
STOCK_READ_LEVEL_ROUND_SPAN_PCT = 0.25      # round numbers listed within 25% of the price
STOCK_READ_LEVEL_AT_PCT = 0.002             # a zone this close to the price is "at" it ...
STOCK_READ_LEVEL_AT_MIN = 0.01              # ... and a cent always is
STOCK_READ_DAILY_LEVEL_SESSIONS = 60        # daily highs and lows looked at, left of today
STOCK_READ_DAILY_LEVEL_TOUCH_PCT = 0.02     # daily highs (lows) within 2% of each other are one level
STOCK_READ_DAILY_MERGE_PCT = 0.015          # daily levels within 1.5% are one zone
STOCK_READ_DAILY_STAIR_MAX = 3              # the older daily highs above the price kept ("look left and up")
STOCK_READ_DAILY_SMA_DAYS = 200             # the 200-day average (stored daily bars close after hours)
STOCK_READ_ROOM_MIN_R = 2.0                 # Room under this many R reads amber: trial T7 decides more
STOCK_READ_ROUND_NEAR_SHARE = 0.1           # a target or stop within a tenth of a step of a round (5c at a half dollar)
STOCK_READ_ROUND_FRESH_BARS = 15            # a cross is fresh when the 15 candles before it stayed on the other side
STOCK_READ_ROUND_CROSS_SEC = 10 * 60        # "broke $X" / "lost $X" is said this long after the cross
# The round numbers a price is watched at (operator report 2026-10-01: ACN at $223 listed every half dollar
# from its stop to its target -- 26 lines, a ruler of labels on top of each other, and the real tops and
# VWAP buried in zones of six half dollars each). A rung is (up to this price, minor step, major step); a
# price takes the first rung that holds it, so its minor step is always 2% of the price or more, as a half
# dollar is on a $25 stock. The level study measured the first rung, on $1-$20 stocks; the rest are not
# measured, and the plan says so instead of quoting the study.
STOCK_READ_ROUND_LADDER = (
    (25.0, 0.5, 1.0),           # half and whole dollars
    (50.0, 1.0, 5.0),
    (125.0, 2.5, 10.0),
    (250.0, 5.0, 10.0),
    (500.0, 10.0, 50.0),
    (1250.0, 25.0, 100.0),
    (2500.0, 50.0, 100.0),
    (float("inf"), 100.0, 500.0),
)
STOCK_READ_ROUND_MEASURED_MIN = 1.0         # the level study's stocks were $1-$20
STOCK_READ_ROUND_MEASURED_MAX = 20.0
# What the level study measured (in sample, 2021-09..2026-09 minute bars of the pillar stocks, $1-$20;
# F:\Nova\eyes\studies\levels-2026-09-30). Each pair is (at the level, at a random price) in percent.
STOCK_READ_LEVEL_STUDY = {
    "source": "5 years of minute bars on the pillar stocks, $1-$20, in sample (2026-09-30)",
    "round_turn": (24, 16),      # a fresh approach to a half / whole dollar turned back before printing through
    "round_through": (77, 70),   # once 1c through: +1.5% before -1.5% (whole dollars 78)
    "round_lost": (68, 63),      # a break under: -1.5% before +1.5%
    "hod_past": (72, 77),        # a backtest trade that reached the high of day went 0.5R past it
    "top_past": (71, 76),        # ... a top tested twice or more
    "daily_past": (78, 78),      # ... an old daily high: no effect
}

# -- the trade you hold (ADR 036 amendment 2026-10-01) -------------------------------------------------
STOCK_READ_HELD_SCHEMA_VERSION = 1
STOCK_READ_HELD_BROKE_ROWS = 2              # the ladder lists at most this many broke rounds under the price
STOCK_READ_FLUSH_WINDOW_SEC = 30.0          # trial T1's flow window: a flush call reads 30 s of tape
STOCK_READ_FLUSH_SCHEMA_VERSION = 1

# -- the history ---------------------------------------------------------------------------------------
STOCK_READ_RUN_MIN_PCT = 0.40               # a run: a session whose high was 40% or more over the prior close
STOCK_READ_HISTORY_READ_DAYS = 260          # daily bars read for the runs (about a year)
STOCK_READ_HISTORY_CHART_DAYS = 120         # daily bars sent for the history chart
STOCK_READ_SETUPS_HISTORY_DAYS = 365        # armed setups on the symbol counted this far back

# -- dilution on file (the float group's row; operator ask 2026-10-01) ---------------------------------
# What SEC EDGAR lists for the symbol's registrant (stock_read/dilution.py). A window is counted in days
# from a filing's date to today's Eastern date, the day itself included.
STOCK_READ_DILUTION_SOURCE = "sec_edgar"    # the row's ``source``
STOCK_READ_DILUTION_SHELF_FORMS = ("S-3", "S-3/A", "S-3ASR", "F-3", "F-3/A", "F-3ASR")
STOCK_READ_DILUTION_SHELF_DAYS = 3 * 365    # a shelf registration filed within the last three years
STOCK_READ_DILUTION_PROSPECTUS_PREFIX = "424B"   # any 424B*: 424B1 .. 424B8
STOCK_READ_DILUTION_PROSPECTUS_DAYS = 180
STOCK_READ_DILUTION_S1_FORMS = ("S-1", "S-1/A", "F-1", "F-1/A")
STOCK_READ_DILUTION_S1_DAYS = 180
STOCK_READ_DILUTION_PLACEMENT_FORMS = ("8-K",)
STOCK_READ_DILUTION_PLACEMENT_ITEM = "3.02"      # an 8-K's Item 3.02: unregistered sales of equity securities
STOCK_READ_DILUTION_PLACEMENT_DAYS = 180
STOCK_READ_DILUTION_KEEP_PER_KIND = 20      # filings kept per kind, the newest; a count past it reads "20+"
# The read of EDGAR (stock_read/dilution_reader.py): in the background, asked by the stock read, never
# waited for.
STOCK_READ_DILUTION_ENV = "NOVA_DILUTION_READER"     # "0" turns the reader off (the row then says so)
STOCK_READ_DILUTION_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
STOCK_READ_DILUTION_PAGE_URL = "https://data.sec.gov/submissions/{name}"   # an older page of the same list
STOCK_READ_DILUTION_PAGE_NAME_RE = r"^CIK\d{10}-submissions-\d{3}\.json$"
STOCK_READ_DILUTION_TTL_SEC = 24 * 3600.0   # a read is reused for a day at most ...
STOCK_READ_DILUTION_DAY_START_HOUR_ET = 4   # ... and never across 04:00 ET: a session's first ask reads last night's filings
STOCK_READ_DILUTION_TICKERS_TTL_SEC = 24 * 3600.0    # SEC's ticker -> CIK list, kept in memory this long
# SEC fair access allows 10 requests a second for the whole desk. The catalyst feed paces its own at up
# to 6.7 a second (CATALYST_FEED_SEC_MIN_GAP_SEC); this reader adds one, so the two stay under 8.
STOCK_READ_DILUTION_SEC_MIN_GAP_SEC = 1.0
STOCK_READ_DILUTION_RETRY_SEC = (30.0, 120.0, 600.0)  # after a failed read: the 1st, 2nd, then every later wait
# EDGAR's ``recent`` block holds a year or 1,000 filings, whichever is more; older ones are in pages of
# about 2,000. Pages are read only when at most this many reach back to the shelf window's start (a bank
# that files thousands of notes a year would need dozens: its shelf is then stated as not known).
STOCK_READ_DILUTION_MAX_PAGES = 2
STOCK_READ_DILUTION_DB_DIRNAME = "stock_read"
STOCK_READ_DILUTION_DB_FILENAME = "dilution.sqlite3"
STOCK_READ_DILUTION_DB_SCHEMA_VERSION = 1
STOCK_READ_DILUTION_SQLITE_TIMEOUT_SEC = 30.0
STOCK_READ_DILUTION_KEEP_DAYS = 30          # a symbol nobody asked about for this long leaves the cache

# -- serving -------------------------------------------------------------------------------------------
STOCK_READ_CACHE_SEC = 2.0                  # one read per (symbol, entry, stop) serves every poll inside this
STOCK_READ_BARS_LIMIT = 1000                # one 04:00-20:00 session of 1-min bars (960)
STOCK_READ_BARS_5M_LIMIT = 400              # 5-min bars read for the 5-minute MACD (two sessions and more)
STOCK_READ_DECISIONS_MAX_EVENTS = 400       # a day's timeline is cut here (oldest kept, a note says so)
STOCK_READ_AUDIT_TAIL = 2000                # bot audit lines read for one symbol's day
STOCK_READ_DECISIONS_CACHE = 16             # (date, symbol, journal size) timelines kept in memory
