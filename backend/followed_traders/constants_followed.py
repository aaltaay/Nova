"""Followed traders tunables. Owner: backend/followed_traders/. Schema: architecture/schema/followed-traders.md.

Mirrors: frontend/src/followed_traders/constants.ts (``FOLLOWED_REFRESH_MS``, ``FOLLOWED_CAPTURE_STALE_SEC``).
"""
from __future__ import annotations

FOLLOWED_SCHEMA_VERSION = 1
# The feed's base URL (e.g. http://127.0.0.1:8787). Unset: no route, no tab, no request to any feed.
FOLLOWED_FEED_URL_ENV = "NOVA_FOLLOW_FEED_URL"

# -- the feed ------------------------------------------------------------------------------------
FOLLOWED_FEED_TIMEOUT_SEC = 3.0
FOLLOWED_EVIDENCE_MAX_BYTES = 2 * 1024 * 1024
# The feed's read log for a day (one line per changed read), and the reads one answer carries.
FOLLOWED_READS_MAX_BYTES = 16 * 1024 * 1024
FOLLOWED_READS_MAX = 2000
FOLLOWED_USER_AGENT = "Nova followed-traders"
# The page calls the feed's capture stopped when its status is older than this.
FOLLOWED_CAPTURE_STALE_SEC = 60
# A trader left the bar once it has been read without them, beside the day's other traders, for this long.
FOLLOWED_LEFT_BAR_SEC = 60.0
# The day's read log is asked of the feed at most this often for a date (the page asks /day every 3 s).
FOLLOWED_SEEN_CACHE_SEC = 10.0

# -- Level 1 lines for open positions -------------------------------------------------------------
FOLLOWED_LINE_OWNER = "followed"
FOLLOWED_MAX_LINES = 10
# The lines are released when no request came for this long (the page polls every FOLLOWED_REFRESH_MS).
FOLLOWED_WANTED_SEC = 20.0
# A line still missing (opened five at a time, dropped by a reconnect, failed) is asked for again this often.
FOLLOWED_LINE_RECONCILE_SEC = 5.0

# -- exits, from IBKR's historical trades ----------------------------------------------------------
# A point exit is the last price-setting trade at or before the exit, looked for this far back.
FOLLOWED_EXIT_LOOKBACK_SEC = 600.0
# A window's trades are read in at most this many of IBKR's 1,000-trade pages, else 1-minute bars.
FOLLOWED_EXIT_MAX_PAGES = 3
FOLLOWED_EXIT_PAGE_TIMEOUT_SEC = 10.0
# Historical requests left for charts in IBKR's 10-minute budget before an exit read waits.
FOLLOWED_EXIT_HEADROOM = 20
FOLLOWED_EXIT_RETRY_SEC = 15.0       # after a shed (pacing, an open chart loading)
FOLLOWED_EXIT_FAIL_RETRY_SEC = 60.0  # after a failure
FOLLOWED_EXIT_MAX_TRIES = 3          # failures before the exit reads unavailable
FOLLOWED_EXIT_BARS_LIMIT = 1200      # 1-minute bars asked of the chart's store for a window fallback
# Exits read as one price or a range, kept in the operator cache (owner: followed_traders/exits.py).
FOLLOWED_EXITS_FILE = "followed-exits.json"
FOLLOWED_EXITS_SCHEMA_VERSION = 1

# -- a ticker the feed may have read glued to its price (tickers.py) -------------------------------
# A trade's first price fits IBKR's tape at its entry within this many percent (the price at that second, or the
# range of an entry window widened as much). A glued reading is 2x or more away from the true one.
FOLLOWED_TICKER_FIT_PCT = 1.5
# An exit or entry tape asked for a ticker IBKR does not know reads unavailable with this, at once.
FOLLOWED_NO_SUCH_TICKER = "IBKR has no such ticker"
# An add moves a trader's average toward the price they paid, so it never doubles or halves it (the feed's own
# GLUE_PRICE_FACTOR): an average read this far from the one before it is a glued read put back, or a misread.
FOLLOWED_AVG_FACTOR = 2.0

# -- starting the feed again when it stops (keeper.py) ---------------------------------------------
# The Windows scheduled task that starts the feed (e.g. "TraderTV Feed"). Unset: Nova starts nothing.
FOLLOWED_FEED_TASK_ENV = "NOVA_FOLLOW_FEED_TASK"
FOLLOWED_KEEPER_TICK_SEC = 30.0
# Not answering this long (two asks in a row) is a stopped feed.
FOLLOWED_KEEPER_DOWN_SEC = 25.0
# Weekdays from..until ET the capture should be reading: from just after the task's own 07:55 start to the capture's
# own 16:30 end of day. In those hours a capture with no sign of life for this long is started again.
FOLLOWED_KEEPER_CAPTURE_FROM_ET = "07:56"
FOLLOWED_KEEPER_CAPTURE_UNTIL_ET = "16:30"
FOLLOWED_KEEPER_STALE_SEC = 600.0
# At most one run this often: each start of the capture asks YouTube for the stream, and asks close together get the
# network a "confirm you're not a bot" wall.
FOLLOWED_KEEPER_COOLDOWN_SEC = 600.0
FOLLOWED_KEEPER_RUN_TIMEOUT_SEC = 15.0
FOLLOWED_KEEPER_HOSTS = ("127.0.0.1", "localhost", "::1")

# -- records ------------------------------------------------------------------------------------
FOLLOWED_RECORD_RANGES = ("day", "week", "all")
FOLLOWED_RECORD_WEEK_DAYS = 7        # "week": the seven calendar days ending on the day asked

# -- errors --------------------------------------------------------------------------------------
FOLLOWED_ERR_BAD_DATE = "FOLLOWED_BAD_DATE"
FOLLOWED_ERR_BAD_RANGE = "FOLLOWED_BAD_RANGE"
FOLLOWED_ERR_FEED_UNREACHABLE = "FOLLOWED_FEED_UNREACHABLE"
FOLLOWED_ERR_BAD_READS = "FOLLOWED_BAD_READS"
