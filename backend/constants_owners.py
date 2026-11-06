"""Your book and the bots' book's constants (ADR 069, ``architecture/schema/recording-and-replay.md``)."""
from __future__ import annotations

from constants_loss_limit import LOSS_LIMIT_BOT_CLOSE_ORIGINS, LOSS_LIMIT_LINE_BOTS, LOSS_LIMIT_LINE_YOU

# The two books: the wire's ``owner``. The same words as the loss limit's You and Bots lines (ADR 063).
OWNER_YOU = LOSS_LIMIT_LINE_YOU
OWNER_BOTS = LOSS_LIMIT_LINE_BOTS
OWNERS = (OWNER_YOU, OWNER_BOTS)

# Who holds shares inside a book: the wire's ``bot`` (null for yours). A bots' order names its bot by its
# origin; one with no origin it can name is the strategy bot's.
HOLDER_YOU = OWNER_YOU
HOLDER_STRATEGY_BOT = "bot"
HOLDER_AUTO_ENTRY = "auto_entry"
BOT_HOLDERS = (HOLDER_STRATEGY_BOT, HOLDER_AUTO_ENTRY, "bot_api", "live_trader", "claude")
# Auto-entry buys for you and hands you the exit (stock mode): its shares are the bots' book, and your Sell and
# Flatten may close them too, after your own (the operator, 2026-11-03).
YOURS_TO_SELL = (HOLDER_YOU, HOLDER_AUTO_ENTRY)
# A close of the whole bots' book, not one bot's: the Bots line's Auto sell and the operator's Close on a
# bots' row. It closes every bot's shares in the stock, in proportion to what each holds.
HOLDER_BOTS_BOOK = OWNER_BOTS
ORIGIN_CLOSE_BOTS = "close_bots"
BOTS_BOOK_CLOSE_ORIGINS = ("loss_limit_bots", ORIGIN_CLOSE_BOTS)
# A bot's own close (sent as source ``flatten`` with the bot's origin) is the bots' (ADR 063).
BOT_CLOSE_ORIGINS = (*LOSS_LIMIT_BOT_CLOSE_ORIGINS, ORIGIN_CLOSE_BOTS)

# The trade journal on the Reports tab (ADR 069 decision 6, architecture/schema/journal.md): a read asks for
# ``live`` -- every row that is not Paper's (IBKR round trips and imported files, the journal as it was) -- or
# ``paper``, Paper's round trips, one per holder.
JOURNAL_VENUE_LIVE = "live"
JOURNAL_VENUE_PAPER = "paper"
JOURNAL_VENUES = (JOURNAL_VENUE_LIVE, JOURNAL_VENUE_PAPER)

# The bots' budget (ADR 069 decision 5): every bot together, open positions at the mark plus working
# entries at their limit, on Paper. The operator's setting, in the operator cache.
OWNERS_BUDGET_FILE = "owners-budget.json"
OWNERS_BUDGET_SCHEMA_VERSION = 1
OWNERS_BOTS_BUDGET_DEFAULT_USD = 25_000
OWNERS_BOTS_BUDGET_MIN_USD = 0
OWNERS_BOTS_BUDGET_MAX_USD = 10_000_000

# Refusals on Paper (ADR 069 decisions 2-5), each said in words.
OWNERS_BOT_STAYS_OUT_CODE = "OWNERS_BOT_STAYS_OUT"
OWNERS_OTHER_SIDE_CODE = "OWNERS_OTHER_SIDE"
OWNERS_NOT_YOURS_CODE = "OWNERS_NOT_YOURS"
OWNERS_BOTS_BUDGET_CODE = "OWNERS_BOTS_BUDGET"
OWNERS_REASON_INVALID = "OWNERS_BUDGET_INVALID"
OWNERS_REASON_NOTHING_TO_CLOSE = "OWNERS_NOTHING_TO_CLOSE"

# How a holder is named in the words Nova says (the Bots page's names).
HOLDER_NAMES = {
    HOLDER_YOU: "You",
    HOLDER_STRATEGY_BOT: "The strategy bot",
    "auto_entry": "Auto-entry",
    "bot_api": "The bot API",
    "live_trader": "The Live Trader",
    "claude": "Claude",
    HOLDER_BOTS_BOOK: "The bots",
}

