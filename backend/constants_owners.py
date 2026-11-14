"""The three traders' books' constants (ADR 072, ``architecture/schema/traders.md``).

Each account (Paper, and Sim's scratch account) keeps one cash and, inside it, a book per trader -- you, Claude and
the brain -- plus read-only Earlier bots: what the retired bots held and traded (ADR 069's bots' book).
"""
from __future__ import annotations

from constants_loss_limit import LOSS_LIMIT_LINE_YOU

# The wire's ``owner``. The same word as the loss limit's You line.
OWNER_YOU = LOSS_LIMIT_LINE_YOU
OWNER_CLAUDE = "claude"
OWNER_BRAIN = "brain"
OWNER_EARLIER_BOTS = "earlier_bots"
OWNERS = (OWNER_YOU, OWNER_CLAUDE, OWNER_BRAIN)              # the three traders
AI_TRADERS = (OWNER_CLAUDE, OWNER_BRAIN)                     # the two with an On / Off switch
BOOKS = (*OWNERS, OWNER_EARLIER_BOTS)                         # every book a split reads, in the order it reads them
OWNER_NAMES = {OWNER_YOU: "You", OWNER_CLAUDE: "Claude", OWNER_BRAIN: "The brain", OWNER_EARLIER_BOTS: "Earlier bots"}

# Who holds shares: you, Claude, the brain, or a retired bot by its origin (the wire's ``bot`` on Earlier bots).
HOLDER_YOU = OWNER_YOU
HOLDER_STRATEGY_BOT = "bot"
HOLDER_AUTO_ENTRY = "auto_entry"
EARLIER_BOT_HOLDERS = (HOLDER_STRATEGY_BOT, HOLDER_AUTO_ENTRY, "bot_api", "live_trader")
# A close of every holder but you (ADR 069's whole bots' book): the Bots line's Auto sell, and your Close on a bots'
# row in a ledger written before ADR 072. It reads as Earlier bots' order and closes the others' shares in proportion.
HOLDER_BOTS_BOOK = "bots"
ORIGIN_CLOSE_BOTS = "close_bots"
BOTS_BOOK_CLOSE_ORIGINS = ("loss_limit_bots", ORIGIN_CLOSE_BOTS)
# Each AI trader's own loss line's Auto sell is that trader's (ADR 072 decision 8).
TRADER_LOSS_ORIGINS = {"loss_limit_claude": OWNER_CLAUDE, "loss_limit_brain": OWNER_BRAIN}
# The cancels a switch turned Off makes, and the cancels of a trader's resting exits before your close of a handed
# position (``execution.md``, origin ``takeover``).
ORIGIN_TAKEOVER = "takeover"
TAKEOVER_CODE = "TAKEOVER"

# The trade journal on the Reports tab (ADR 069 decision 6, architecture/schema/journal.md): a read asks for
# ``live`` -- every row that is not Paper's (IBKR round trips and imported files, the journal as it was) -- or
# ``paper``, Paper's round trips, one per holder.
JOURNAL_VENUE_LIVE = "live"
JOURNAL_VENUE_PAPER = "paper"
JOURNAL_VENUES = (JOURNAL_VENUE_LIVE, JOURNAL_VENUE_PAPER)

# Refusals on Paper and Sim (ADR 072 decisions 3-5, ``owners.rules``), each said in words.
OWNERS_TRADERS_STOCK_CODE = "OWNERS_TRADERS_STOCK"
OWNERS_TRADER_ON_CODE = "OWNERS_TRADER_ON"
OWNERS_BUDGET_CODE = "OWNERS_BUDGET"
OWNERS_OTHER_SIDE_CODE = "OWNERS_OTHER_SIDE"
OWNERS_NOT_YOURS_CODE = "OWNERS_NOT_YOURS"

# How a holder is named in the words Nova says.
HOLDER_NAMES = {
    HOLDER_YOU: "You",
    OWNER_CLAUDE: "Claude",
    OWNER_BRAIN: "The brain",
    HOLDER_STRATEGY_BOT: "The strategy bot",
    HOLDER_AUTO_ENTRY: "Auto-entry",
    "bot_api": "The bot API",
    "live_trader": "The Live Trader",
    HOLDER_BOTS_BOOK: "The bots",
}
