"""Short selling tunables and reason codes (ADR 048).

Owner: backend/short_sale/. Not re-exported from the constants barrel: only the short check
and its readers import them.

The margin numbers are the published rules the operator's plan states (ADR 048 decision 2),
used when IBKR's what-if cannot answer; the cushion, the equity floor and the hours are the
operator's rules. Numbers marked CHOSEN were left open by the plan.
"""
from __future__ import annotations

# -- The published maintenance a short needs, per share (FINRA 4210(c) and IBKR's short rules).
SHORT_MAINT_LOW_PRICE = 2.50          # under this price: SHORT_MAINT_LOW_PER_SHARE a share
SHORT_MAINT_LOW_PER_SHARE = 2.50
SHORT_MAINT_MID_PRICE = 5.00          # SHORT_MAINT_LOW_PRICE up to this: 100% of value
SHORT_MAINT_MID_PER_SHARE = 5.00      # SHORT_MAINT_MID_PRICE up to SHORT_MAINT_HIGH_PRICE: this a share
SHORT_MAINT_HIGH_PRICE = 16.67        # above this: SHORT_MAINT_HIGH_PCT of value
SHORT_MAINT_HIGH_PCT = 0.30
LONG_MAINT_PCT = 0.25                 # a long's published maintenance: 25% of value

# -- The account a short needs.
SHORT_MIN_EQUITY = 2_000.0            # FINRA 4210(b)(2): no credit, so no short, under this equity
SHORT_CUSHION_PCT = 0.25              # IBKR must not liquidate within a 25% move against the short
SHORT_MARGIN_SOURCE_PUBLISHED = "published rules"   # the label a figure from these rules carries

# -- The liquidation price solver (short_sale.margin): bisection steps and the price it stops at.
SHORT_LIQ_BISECT_STEPS = 60
SHORT_LIQ_TOLERANCE = 1e-6

# -- Reason codes the short check refuses with (ADR 009's SHORT_DISABLED, SHORT_NOT_SHORTABLE and
# SHORT_STALE_BORROW stay in ibkr.shortability / execution.validate).
SHORT_WHILE_LONG = "SHORT_WHILE_LONG"             # the account holds the stock long: Nova never flips
SHORT_NOT_MARGIN = "SHORT_NOT_MARGIN"             # the account is not a margin account
SHORT_EQUITY = "SHORT_EQUITY"                     # equity under SHORT_MIN_EQUITY
SHORT_MARGIN = "SHORT_MARGIN"                     # the requirement does not fit the account
SHORT_MARGIN_UNKNOWN = "SHORT_MARGIN_UNKNOWN"     # the account's equity or margin cannot be read
SHORT_CUSHION = "SHORT_CUSHION"                   # IBKR would liquidate within SHORT_CUSHION_PCT
SHORT_BORROW_TOO_SMALL = "SHORT_BORROW_TOO_SMALL"  # borrow does not cover the order + short + in flight
SHORT_NEEDS_LIMIT = "SHORT_NEEDS_LIMIT"           # a short entry is a limit order (ADR 048 1.6)
SHORT_NEEDS_STOP = "SHORT_NEEDS_STOP"             # a short goes out with its buy stop above the entry (1.6)
SHORT_HOURS = "SHORT_HOURS"                       # outside 09:35 to 15:50 ET by the venue's clock (1.9)
SHORT_HALTED = "SHORT_HALTED"                     # the stock is halted (1.8)
SHORT_HALT_COOLOFF = "SHORT_HALT_COOLOFF"         # within 10 minutes of an up-halt's resumption (1.8)
SHORT_HALT_UNKNOWN = "SHORT_HALT_UNKNOWN"         # Nova cannot tell whether the stock is halted (1.8)
SHORT_SSR_AT_BID = "SHORT_SSR_AT_BID"             # under SSR, a short priced at or below the bid (1.10)
SHORT_SSR_NO_BID = "SHORT_SSR_NO_BID"             # under SSR, no bid to price above (1.10)
SHORT_NO_RECORDED_BORROW = "SHORT_NO_RECORDED_BORROW"  # a past-day replay with no borrow recorded then (4)
SHORT_REPRICE = "SHORT_REPRICE"                   # a working short entry is never repriced in place

# -- The hours (ADR 048 1.9 and 5): new shorts from 09:35 ET until ten minutes before the close
# (15:50, or 12:50 on an NYSE early close); the day cover five minutes before it (15:55 / 12:55).
SHORT_OPEN_MIN_ET = 9 * 60 + 35
SHORT_LAST_ENTRY_LEAD_MIN = 10
SHORT_COVER_LEAD_MIN = 5

# -- Halts (ADR 048 1.8): no short for this long after an up-halt resumes; a halt is "up" when the
# last price before it is over the price this long before (or LULD had it at the upper band).
SHORT_HALT_COOLOFF_SEC = 600.0
SHORT_HALT_DIRECTION_LOOKBACK_SEC = 300.0

# -- SSR (Reg SHO Rule 201): a trade this far under the prior close restricts shorts for the rest of
# the day and all of the next.
SSR_TRIGGER_FRACTION = 0.10

# -- IBKR's what-if (ADR 048 decision 2): how long one answer is read as fresh, how long a stock's
# answer is kept as its ratio, how long the read-only check and the door wait for one (a bot's
# short; the ticket never waits: ADR 045's deadline).
SHORT_WHATIF_FRESH_SEC = 60.0
SHORT_WHATIF_KEEP_SEC = 8 * 3600.0
SHORT_WHATIF_TIMEOUT_SEC = 2.0
SHORT_WHATIF_BOT_WAIT_SEC = 1.5
SHORT_WHATIF_WORKERS = 1
SHORT_MARGIN_SOURCE_WHATIF = "IBKR what-if"

# -- Borrow, recorded (ADR 048 decision 4): every tick-236 read, kept for good, so a past-day Sim
# replay knows what IBKR said then. NOVA_BORROW_DIR; else F:\Nova\borrow while F: is mounted; else
# <cache>/borrow. NOVA_BORROW_LOG=0 turns the recording off.
BORROW_DIR_ENV = "NOVA_BORROW_DIR"
BORROW_LOG_ENV = "NOVA_BORROW_LOG"
BORROW_DEFAULT_ROOT_WIN = "F:\\Nova\\borrow"
BORROW_DB_FILENAME = "borrow.sqlite3"
BORROW_SCHEMA_VERSION = 1
BORROW_LOG_QUEUE_MAX = 10_000
BORROW_LOG_BATCH = 500
BORROW_SQLITE_TIMEOUT_SEC = 5.0
# The SSR read's IBKR history (two daily reads a stock, a day): asked again this long after a miss.
SSR_HISTORY_RETRY_SEC = 120.0
SSR_HISTORY_DURATION = "5 D"
SSR_HISTORY_TIMEOUT_SEC = 20.0
SSR_HISTORY_WORKERS = 1
# Paper and Sim fill an SSR short only above the bid (ADR 048 decision 4); the SSR read a fill asks
# is reused for this long (the fills of one burst of prints read it once).
SSR_FILL_MEMO_SEC = 5.0

# -- Nova's own closes on Paper and Sim (the day cover, the margin call): a pass this often.
# NOVA_SHORT_RUNNER=0 turns the loop off (the tests drive short_sale.closes directly).
SHORT_RUNNER_INTERVAL_SEC = 1.0
SHORT_RUNNER_ENV = "NOVA_SHORT_RUNNER"
# A close the venue refused is tried again this long after (wall clock), not on every pass.
SHORT_CLOSE_RETRY_SEC = 15.0
