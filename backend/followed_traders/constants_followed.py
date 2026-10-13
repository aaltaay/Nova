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
FOLLOWED_USER_AGENT = "Nova followed-traders"
# The page calls the feed's capture stopped when its status is older than this.
FOLLOWED_CAPTURE_STALE_SEC = 60

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

# -- records ------------------------------------------------------------------------------------
FOLLOWED_RECORD_RANGES = ("day", "week", "all")
FOLLOWED_RECORD_WEEK_DAYS = 7        # "week": the seven calendar days ending on the day asked

# -- errors --------------------------------------------------------------------------------------
FOLLOWED_ERR_BAD_DATE = "FOLLOWED_BAD_DATE"
FOLLOWED_ERR_BAD_RANGE = "FOLLOWED_BAD_RANGE"
FOLLOWED_ERR_FEED_UNREACHABLE = "FOLLOWED_FEED_UNREACHABLE"
