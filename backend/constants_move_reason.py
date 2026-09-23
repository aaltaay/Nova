"""Why it's moving (ADR 028): the rule thresholds and the borrow feed's settings.

The thresholds are a trader's rules of thumb, not fitted parameters: a float under 10M is the operator's
own low-float line (``LEADERS_RULES``), a squeeze needs shorts worth a fifth of the float or three days
to cover, and a borrow fee of 50% a year is expensive.
"""
from __future__ import annotations

MOVE_RULES_VERSION = "move-rules-v1-2026-09-23"
MOVE_SCHEMA_VERSION = 1

# Likely causes, in the order the rules try them.
MOVE_KIND_NOT_MOVING = "not_moving"
MOVE_KIND_NEWS_PENDING = "news_pending"
MOVE_KIND_NEWS = "news"
MOVE_KIND_SHORT_SQUEEZE = "short_squeeze"
MOVE_KIND_ROUTINE_NEWS = "routine_news"
MOVE_KIND_SPLIT_SQUEEZE = "split_squeeze"
MOVE_KIND_LOW_FLOAT_MOMENTUM = "low_float_momentum"
MOVE_KIND_THIN_TRADING = "thin_trading"
MOVE_KIND_UNEXPLAINED = "unexplained"

MOVE_STATE_YES = "yes"
MOVE_STATE_NO = "no"
MOVE_STATE_UNKNOWN = "unknown"
MOVE_CONFIDENCE_LIKELY = "likely"
MOVE_CONFIDENCE_POSSIBLE = "possible"

# -- thresholds ------------------------------------------------------------------------------------
MOVE_MIN_CHANGE = 0.10                 # a move under 10% either way is not read for a cause
MOVE_LOW_FLOAT_SHARES = 10_000_000     # the operator's low-float line (LEADERS_RULES)
MOVE_ROTATION_HIGH = 3.0               # the float traded at least three times over today
MOVE_ROTATION_SQUEEZE = 1.0            # a squeeze needs the float to have traded at least once
MOVE_ROTATION_THIN = 0.1               # under a tenth of the float traded: thin
MOVE_RVOL_SQUEEZE = 3.0                # ... or three times the usual volume
MOVE_RVOL_THIN = 1.0                   # below the usual volume
MOVE_SHORT_PCT_HIGH = 0.20             # shorts worth a fifth of the float
MOVE_DAYS_TO_COVER_HIGH = 3.0
MOVE_BORROW_FEE_HIGH = 50.0            # IBKR's annual fee, percent
MOVE_BORROW_FEE_JUMP = 2.0             # the fee doubled since the open ...
MOVE_BORROW_FEE_JUMP_MIN = 20.0        # ... and is at least 20%
MOVE_BORROW_AVAILABLE_DROP = 0.75      # three quarters of the lendable shares gone since the open
MOVE_BORROW_SCARCE_SHARES = 10_000     # fewer than this to lend is scarce
MOVE_SPLIT_RECENT_DAYS = 10            # a reverse split this recent still shapes the supply
MOVE_NEWS_HALT_CODES = ("T1", "T2", "T3", "T12")
MOVE_VOLATILITY_HALT_CODES = ("M",)
MOVE_LULD_HALT_KINDS = ("LUDP", "luld")

# -- the borrow feed (move_reason/borrow_feed.py) --------------------------------------------------
MOVE_BORROW_FEED_ENV = "NOVA_BORROW_FEED"              # "0" turns the feed off
MOVE_BORROW_URL = "ftp://shortstock:@ftp2.interactivebrokers.com/usa.txt"
MOVE_BORROW_POLL_SEC = 900.0                          # IBKR refreshes the file about every 15 minutes
MOVE_BORROW_RETRY_SEC = 120.0                         # after a failed poll
MOVE_BORROW_HTTP_TIMEOUT_SEC = 60.0
MOVE_BORROW_CURRENCY = "USD"
MOVE_BORROW_CAPPED_SHARES = 10_000_000                # the file writes ">10000000" above this
MOVE_BORROW_DB_DIRNAME = "move_reason"
MOVE_BORROW_DB_FILENAME = "borrow.sqlite3"
MOVE_BORROW_SCHEMA_VERSION = 1
MOVE_BORROW_SQLITE_TIMEOUT_SEC = 30.0
MOVE_BORROW_RETENTION_DAYS = 14
MOVE_DAY_START_HOUR_ET = 4                            # the "open" snapshot: first poll at or after 04:00 ET
