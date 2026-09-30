"""Book watcher tunables (ADR 033). Owner: backend/book_watch/.

Observation thresholds only -- nothing here trips, gates or places anything.
"""
from __future__ import annotations

BOOK_WATCH_SCHEMA_VERSION = 1
# NOVA_BOOK_WATCH=0 stops the watcher; NOVA_BOOK_WATCH_JOURNAL=0 stops only its journal.
BOOK_WATCH_ENV = "NOVA_BOOK_WATCH"
BOOK_WATCH_JOURNAL_ENV = "NOVA_BOOK_WATCH_JOURNAL"
BOOK_WATCH_DIR_ENV = "NOVA_BOOK_WATCH_DIR"
BOOK_WATCH_DEFAULT_ROOT_WIN = r"F:\Nova\book_watch"

# IBKR's depth and AllLast lines arrive separately, so a print that took a
# level can land a little before or after the book that shows the level
# smaller. Prints this far either side of the two books count toward the drop.
# Measured on GCTK 2026-09-24 (6,171 drops at the inside): the nearest print at
# the level's price sat within 0.2 s of the books for most drops, with a long
# tail; widening this turns inside pulls into fills but barely moves the flags.
BOOK_WATCH_MATCH_SLACK_SEC = 0.5
# A drop is judged this long after the book that showed it, so a late print
# can still claim it; must exceed the slack.
BOOK_WATCH_SETTLE_SEC = 0.75
# Prints kept for matching.
BOOK_WATCH_PRINT_KEEP_SEC = 10.0
# Prints on these venues trade off the lit book, so they never fill a level.
BOOK_WATCH_OFF_BOOK_EXCHANGES = ("FINRA",)

# A pull is large when it is at least this many shares AND this many times the
# median size of the visible levels on its side.
BOOK_WATCH_LARGE_MIN_SHARES = 1000
BOOK_WATCH_LARGE_MEDIAN_MULT = 4.0
# This many large pulls on one side inside the window is a repeat flag.
BOOK_WATCH_REPEAT_COUNT = 3
BOOK_WATCH_REPEAT_WINDOW_SEC = 60.0
# A side that shrinks to at most this many levels from at least
# BOOK_WATCH_COLLAPSE_FROM is a reset or a glitch, not pulls: that side is unknown.
BOOK_WATCH_COLLAPSE_TO = 1
BOOK_WATCH_COLLAPSE_FROM = 3

# Size that traded at a price beyond the most the book showed there: hidden sellers and
# hidden buyers (hidden.py, ADR 033 amendment 2026-09-30). A print of a cross -- the opening (O), a reopening after a halt
# (5), the closing (6), a cross trade (X) and the official open / close (Q, M) -- traded
# in an auction, not against the book: it never counts, and it ends both sides' stretches
# (GRML 2026-09-22 reopened with one 218,938-share print). A volume-only print (the
# TAPE_NO_PRICE_CONDITIONS codes, less the odd lot, which trades on the book like any
# other; B, a bunched trade) never counts either.
BOOK_WATCH_AUCTION_CONDITIONS = frozenset("O56XQM")
BOOK_WATCH_HIDDEN_SKIP_CONDITIONS = frozenset("CHMNPQRUVW479B")
# A stretch is a hidden seller (the ask) or a hidden buyer (the bid) once its price has held
# this long since its first print, this many shares printed there, and at least this many
# times the most the book showed there. Measured on the Session Records 2026-09-21..29
# (tools/hidden_study.py, 26 hours with a book): without the hold the rule fired mostly on
# sweeps -- a buyer taking the whole offer prints at a price and through it within
# milliseconds -- and said nothing; with 10 s, 2,000 and 3x, a minute after a hidden seller
# the price was past the offer 37% of the time against 46% after an offer that showed its
# size (104 against 66; less often on 4 of 5 days, a tie on the fifth). A hidden buyer showed
# no such difference. A description of the book, not a forecast.
BOOK_WATCH_HIDDEN_MIN_HOLD_SEC = 10.0
BOOK_WATCH_HIDDEN_MIN_SHARES = 2000
BOOK_WATCH_HIDDEN_SHOWN_MULT = 3.0
# A stretch ends after this long without a print at its price.
BOOK_WATCH_HIDDEN_GAP_SEC = 10.0
# The size shown counts from this long before a stretch's first print: what the
# first buyers (or sellers) saw there.
BOOK_WATCH_HIDDEN_SHOWN_BEFORE_SEC = 2.0
# A flagged stretch that keeps growing is sent again at most this often.
BOOK_WATCH_HIDDEN_UPDATE_SEC = 1.0
# Hidden events kept per line for the ladder and the sensor (each update is one).
BOOK_WATCH_HIDDEN_KEEP = 200
BOOK_WATCH_HIDDEN_NOTE = (
    "More traded at that price than the book ever showed there: one hidden (reserve) order or "
    "several orders refilling it look the same here. A description of the book, never a detection."
)

# Readings.
BOOK_WATCH_STATS_WINDOW_SEC = 60.0
BOOK_WATCH_RATE_WINDOW_SEC = 10.0
BOOK_WATCH_FLAGS_KEEP = 50
BOOK_WATCH_PULLS_KEEP = 50
BOOK_WATCH_READ_LIMIT = 20
# Large drops (traded or pulled) kept per line for the Level 2 ladder: BKYI judged
# about 80 a minute on 2026-09-29, so this covers the memory below at several times that.
BOOK_WATCH_DROPS_KEEP = 400

# The Level 2 ladder (ADR 033 amendment, 2026-09-29). A socket that opens is sent
# the large drops of the last minute, so a price pulled before it opened is still
# marked "pulled here"; after that only what the watcher judges next.
BOOK_WATCH_LADDER_MEMORY_SEC = 60.0
# How often a Level 2 socket asks the watcher for new verdicts. A verdict is ready
# BOOK_WATCH_SETTLE_SEC after the book that showed the drop, so a mark reaches the
# ladder about a second after the size left it.
BOOK_WATCH_PUSH_SEC = 0.25
# The per-side totals move with every judged drop; they are sent at most this often.
BOOK_WATCH_SIDES_PUSH_SEC = 1.0
BOOK_WATCH_NOT_LIVE_REASON = (
    "Level 2 is replaying a recording here; the book watcher reads only the live line."
)
BOOK_WATCH_OFF_REASON = "The book watcher is off (NOVA_BOOK_WATCH=0)."
# A line with no book for this long is not being watched; after FORGET it is dropped.
BOOK_WATCH_IDLE_SEC = 5.0
BOOK_WATCH_FORGET_SEC = 3600.0

# Worker.
BOOK_WATCH_QUEUE_MAX = 20000
BOOK_WATCH_TICK_SEC = 0.25
BOOK_WATCH_JOURNAL_QUEUE_MAX = 20000
BOOK_WATCH_JOURNAL_FLUSH_SEC = 1.0

BOOK_WATCH_CAVEATS = (
    "IBKR sends Level 2 in batches: an order posted and pulled between two updates never shows.",
    "Ten rows a side (one row per venue and price): size below them is not seen, and a price at the edge of the rows may be cut off, so it is never judged.",
    "Size only, per price and venue: no order ids and no owners, so nothing here proves who pulled what or why.",
    "Times are when data reached Nova, not the exchange's.",
    "Filled means lit prints at that price inside the matching window; off-exchange (FINRA) prints never fill a level.",
    "Hidden means lit prints at a price that held, beyond the most the book ever showed there; "
    "cross (auction) prints and off-exchange reports never count.",
)
BOOK_WATCH_NOTE = "Hints consistent with spoofing -- never a detection."
