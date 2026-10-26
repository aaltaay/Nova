"""Why it's moving (ADR 028): the rule thresholds and the borrow feed's settings.

The thresholds are a trader's rules of thumb, not fitted parameters: a float under 10M is the operator's
own low-float line (``LEADERS_RULES``), a squeeze needs shorts worth a fifth of the float -- or three days
to cover with at least a tenth of the float short -- and a borrow fee of 50% a year is expensive.
"""
from __future__ import annotations

MOVE_RULES_VERSION = "move-rules-v7-2026-10-26"  # v7: a fund names what it tracks (ADR 028 amendment 4)
# v6 (2026-10-13): "Halts today" names a halt carried over from the prior
# exchange day (``halts.carried``); the news-halt rung reads "No news halt open (T1 / T12)"
# v5 (2026-10-12): the ladder (``likely.steps``); a board's row is read at its own price (``GET /api/why?board=``)
# v4 (2026-10-12): a Sim replay reads its own day as of the playhead; a check names the record it was read from
# and why a fact is unknown (``check_notes``)
# v3 (2026-10-12): days to cover counts only with a tenth of the float short; a Sim replay desk is not read
# v2 (2026-10-02): a filed share issuance makes the float unknown
MOVE_SCHEMA_VERSION = 1

# Likely causes, in the order the rules try them.
MOVE_KIND_NOT_MOVING = "not_moving"
MOVE_KIND_NEWS_PENDING = "news_pending"
MOVE_KIND_NEWS = "news"
MOVE_KIND_FUND = "fund"
MOVE_KIND_SHORT_SQUEEZE = "short_squeeze"
MOVE_KIND_ROUTINE_NEWS = "routine_news"
MOVE_KIND_SPLIT_SQUEEZE = "split_squeeze"
MOVE_KIND_LOW_FLOAT_MOMENTUM = "low_float_momentum"
MOVE_KIND_THIN_TRADING = "thin_trading"
MOVE_KIND_UNEXPLAINED = "unexplained"
# The ladder's first step (``move_reason/explain.py``): the move itself, before any cause.
MOVE_STEP_MOVE = "move"
# Not a cause: a Sim replay where no record reaches the playhead (``routes.not_read_on_replay``).
MOVE_KIND_NOT_READ = "not_read"
MOVE_NOT_READ_REPLAY_DETAIL = ("Nothing Nova recorded reaches this moment -- no board row, replay price, short "
                               "interest, borrow, news, split or halt log -- so it is not read.")

# The batch read (``GET /api/why?symbols=...&board=...``, the Catalyst column).
MOVE_BATCH_MAX_SYMBOLS = 80            # a board holds 50 rows; more symbols than this are refused (400)
MOVE_BATCH_BOARDS = ("gappers", "gainers", "losers", "afterhours", "large_cap")  # strategy.symbol_pillars.raw_boards
# Which price a read used (``facts.priced_by``).
MOVE_PRICED_BY_BOARD_ROW = "board_row"   # the named board's row as it shows it (a frozen board's own price)
MOVE_PRICED_BY_LAST_TRADE = "last_trade"  # the row repriced by the L1 line's last trade (the Trader card)
MOVE_PRICED_BY_ROW = "row"               # a board row the L1 line holds no trade for
MOVE_PRICED_BY_QUOTE = "quote"           # on no board: the L1 quote
MOVE_PRICED_BY_REPLAY = "replay"         # a Sim replay: the loaded replay's print, else the recorded board row

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
MOVE_DAYS_TO_COVER_HIGH = 3.0          # ... or three days to cover (Yahoo's ratio, over the pre-run volume) ...
MOVE_SHORT_PCT_WITH_DTC = 0.10         # ... counted only with a tenth of the float short (proposed 2026-10-12)
MOVE_BORROW_FEE_HIGH = 50.0            # IBKR's annual fee, percent
MOVE_BORROW_FEE_JUMP = 2.0             # the fee doubled since the open ...
MOVE_BORROW_FEE_JUMP_MIN = 20.0        # ... and is at least 20%
MOVE_BORROW_AVAILABLE_DROP = 0.75      # three quarters of the lendable shares gone since the open
MOVE_BORROW_SCARCE_SHARES = 10_000     # fewer than this to lend is scarce
MOVE_SPLIT_RECENT_DAYS = 10            # a reverse split this recent still shapes the supply
MOVE_NEWS_HALT_CODES = ("T1", "T2", "T3", "T12")
MOVE_VOLATILITY_HALT_CODES = ("M",)
MOVE_LULD_HALT_KINDS = ("LUDP", "luld")

# -- a fund names what it tracks (move_reason/fund.py, ADR 028 amendment 4) -------------------------
MOVE_FUND_QUOTE_TYPES = ("ETF", "MUTUALFUND")  # Yahoo's quoteType; Yahoo gives ETNs "ETF" too (BRZD)
MOVE_FUND_TRACKS_MAX_WORDS = 4         # more words left over than this: the name does not say what it tracks
# A multiple the name spells as a word, tried in this order ("UltraPro Short" is 3x).
MOVE_FUND_MULTIPLE_WORDS = (("ultrapro", 3.0), ("ultrashort", 2.0), ("ultra", 2.0))
# Fund sponsors, taken out of the name before what it tracks is read.
MOVE_FUND_ISSUERS = (
    "proshares", "direxion", "defiance", "graniteshares", "t-rex", "rex", "rex shares", "tradr", "microsectors",
    "ishares", "spdr", "vaneck", "invesco", "global x", "ark", "leverage shares", "leverageshares", "valkyrie",
    "kraneshares", "first trust", "wisdomtree", "schwab", "vanguard", "roundhill", "yieldmax", "kurv", "amplify",
    "volatility shares", "axs", "tuttle", "bitwise", "grayscale", "fidelity", "franklin", "jpmorgan", "state street",
    "select sector", "xtrackers", "pacer", "simplify", "bank of montreal", "bmo", "etracs", "ubs", "credit suisse",
    "velocityshares", "ipath", "barclays", "fundstrat", "21shares", "coinshares", "teucrium", "united states",
    "us global", "themes", "neos", "nicholas", "rex-osprey", "osprey", "canary", "hashdex", "wahed", "sprott", "corgi", "capital group", "canary capital group",
)
# Words that say how a fund is built, never what it tracks.
MOVE_FUND_DROP_WORDS = frozenset((
    "daily", "target", "long", "short", "bull", "bear", "inverse", "ultra", "ultrapro", "ultrashort", "leveraged",
    "leverage", "shares", "share", "etf", "etfs", "etn", "etns", "fund", "trust", "index", "capped", "msci", "series",
    "the", "of", "and", "&", "-", "1", "2", "3", "x", "plus", "strategy", "option", "options", "income", "weekly",
    "monthly", "pay", "covered", "call", "premium", "enhanced", "single", "stock", "tracker", "futures", "linked",
    "notes", "note", "exchange", "traded", "class", "a", "b", "inc", "inc.", "corp", "ltd", "plc", "usd", "us",
    "u.s.", "u.s", "equity", "equities", "1x", "2x", "3x", "on", "for", "in", "a-shares", "bull/bear", "active", "ftse",
    "quarterly", "marketvector", "staking", "common", "llc", "l.p.", "lp",
))

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

# -- a Sim replay (move_reason/replay_facts.py): every fact as of the playhead, never after it ------------
MOVE_REPLAY_SHORT_SUBDIR = ("store", "reference", "short_interest")  # under the Massive root (ADR 046)
MOVE_FINRA_PUBLISH_BUSINESS_DAYS = 8   # FINRA publishes about 7 business days after settlement, after the
#                                        close: a settlement counts from the 8th business day on (conservative)
MOVE_REPLAY_SHORT_MONTHS_BACK = 2      # settlement months read before the replayed one
MOVE_REPLAY_SHORT_CACHE = 64           # (month file, symbol) reads kept in memory
