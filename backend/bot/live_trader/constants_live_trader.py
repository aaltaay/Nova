"""The Live Trader bot's tunables (ADR 055). Owner: backend/bot/live_trader/. Schema: architecture/schema/bot.md
("The Live Trader bot").

The defaults are the operator's answers of 2026-10-14 (money and risk, asked as multiple choice). Mirrors:
frontend/src/constantGroups/live_trader.ts (the defaults and bounds the desk shows).
"""
from __future__ import annotations

from constants_practice import PRACTICE_LIVE_FRESH_SEC
from constants_scanner import LARGE_CAP_MIN

LT_SCHEMA_VERSION = 1
LT_VENUE = "paper"                      # the one venue the bot trades (ADR 055: never Live, never Sim)
LT_ORIGIN = "live_trader"               # execution.models.Origin: "Sent by" reads Live Trader
LT_SETUP_PREFIX = "live_trader:"        # the command's setup: live_trader:<HOST>
LT_LINE_OWNER = "live_trader"           # ibkr.ticks owner of the bot's Level 1 lines
LT_AUDIT_ACTION = "live_trader"
LT_KEY_PREFIX = "bot:lt:paper:"         # idempotency keys: bot:lt:paper:<position id>:<step><n>
LT_NAME_MAX = 16                        # a host's name as the feed reads it: 1-16 of A-Z0-9

# -- the files (operator cache) ------------------------------------------------------------------
LT_SETTINGS_FILE = "live-trader-bots.json"
LT_SETTINGS_SCHEMA_VERSION = 1
LT_BOOK_FILE = "live-trader-book.json"
LT_BOOK_SCHEMA_VERSION = 1
LT_CLOSED_KEEP = 200                    # today's closed positions kept in the book

# -- the operator's answers (2026-10-14): each a setting per host --------------------------------
LT_DEFAULT_KEY = False
LT_DEFAULT_ENTRY = "nova"               # stock mode's sides: "you" | "nova" (ADR 037)
LT_DEFAULT_EXIT = "nova"
LT_DEFAULT_STEP_USD = 500.0             # shares = step / price, rounded down; 1 share over the step
LT_DEFAULT_ADDS = 2                     # 0, 2, 4 or None (every add)
LT_DEFAULT_ALLOWANCE_USD = 2500.0
LT_DEFAULT_SIDES = "both"               # "long" | "both"
LT_DEFAULT_SHORT_STOP_PCT = 5.0         # a short's buy stop over its entry
LT_DEFAULT_TAKE_OPEN = True             # positions already open: take one step (within the misread rule)
LT_DEFAULT_SELL_ALL_AT = "15:55"        # ET; the early close's 12:55 comes first (short_sale.hours)

LT_STEP_USD_BOUNDS = (50.0, 10_000.0)
LT_ALLOWANCE_USD_BOUNDS = (100.0, 50_000.0)
LT_ADDS_CHOICES = (0, 2, 4, None)
LT_SIDES = ("long", "both")
LT_SHORT_STOP_PCT_BOUNDS = (1.0, 20.0)
LT_SELL_ALL_BOUNDS = ("09:30", "15:55")

# -- the rules (ADR 055 decisions 2 and 4) --------------------------------------------------------
LT_POLL_SEC = 2.0                       # a pass while a key is on, positions are held or an ask waits
LT_IDLE_SEC = 15.0                      # otherwise: nothing is asked of the feed
LT_FEED_BEHIND_SEC = 30.0               # the page's rule: the read this far behind the stream is doubtful
LT_MISREAD_PCT = 1.5                    # the host's average this far from the market is a misread
LT_ADD_MERGE_SEC = 4.0                  # average changes this close together are one add (an add filling in pieces)
LT_FLICKER_PCT = 0.05                   # an add whose average ends this close to where it began is no add
LT_HIDDEN_SEC = 600.0                   # the bar hidden (or the feed silent) this long: get flat
LT_OPEN_FRESH_SEC = 60.0                # an entry first seen later than this after it happened is already open
LT_WAIT_SEC = 30.0                      # a quote, a market cap or a ticker check waited for this long is a skip
LT_ASK_SEC = 60.0                       # an approval not answered in this long is skipped
LT_QUOTE_FRESH_SEC = PRACTICE_LIVE_FRESH_SEC
LT_MIN_MARKET_CAP_USD = float(LARGE_CAP_MIN)   # large caps only (operator, 2026-10-14)
LT_ENTRY_OFFSET_USD = 0.02              # a long buys at the ask plus this; a short sells at the bid less this
LT_CLOSE_RETRY_SEC = 5.0                # a close not filled (or refused) is sent again after this
LT_CLOSE_MAX_TRIES = 5                  # then the card says to close it by hand, loud
LT_EVENTS_SHOWN = 8                     # a host card's newest events
LT_AUDIT_TAIL_BYTES = 1_000_000         # the cards read the bot audit file's last MB, never the whole file
LT_SKIPS_REMEMBERED = 2000              # skip lines written once per position, step and code (in memory)

# -- skip codes (bot.md "The Live Trader bot", Audit) ----------------------------------------------
LT_FEED_BEHIND = "LT_FEED_BEHIND"
LT_FEED_DOWN = "LT_FEED_DOWN"
LT_TICKER_UNSETTLED = "LT_TICKER_UNSETTLED"
LT_MISREAD = "LT_MISREAD"
LT_SMALL_CAP = "LT_SMALL_CAP"
LT_CAP_UNKNOWN = "LT_CAP_UNKNOWN"
LT_NO_QUOTE = "LT_NO_QUOTE"
LT_ALLOWANCE = "LT_ALLOWANCE"
LT_ADDS_DONE = "LT_ADDS_DONE"
LT_SHORTS_OFF = "LT_SHORTS_OFF"
LT_AGAINST = "LT_AGAINST"
LT_NOT_HELD = "LT_NOT_HELD"
LT_VENUE_CODE = "LT_VENUE"
LT_BOT_OFF = "LT_BOT_OFF"
LT_FROZEN = "LT_FROZEN"
LT_AFTER_SELL_ALL = "LT_AFTER_SELL_ALL"
LT_SHORT_HOURS = "LT_SHORT_HOURS"
LT_NOT_PRICEABLE = "LT_NOT_PRICEABLE"
LT_ASK_EXPIRED = "LT_ASK_EXPIRED"
LT_ASK_SKIPPED = "LT_ASK_SKIPPED"
LT_ALREADY_OPEN = "LT_ALREADY_OPEN"
LT_OFF_AIR = "LT_OFF_AIR"
LT_HIDDEN = "LT_HIDDEN"
LT_DAY_LOCK = "LT_DAY_LOCK"
LT_NOT_ON_BAR = "LT_NOT_ON_BAR"

# -- route errors ---------------------------------------------------------------------------------
LT_ERR_INVALID = "LIVE_TRADER_INVALID"
LT_ERR_SETTINGS_UNREADABLE = "LIVE_TRADER_SETTINGS_UNREADABLE"
LT_ERR_ASK_GONE = "LIVE_TRADER_ASK_GONE"
