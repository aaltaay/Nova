"""Book watcher tunables (ADR 031). Owner: backend/book_watch/.

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

# Readings.
BOOK_WATCH_STATS_WINDOW_SEC = 60.0
BOOK_WATCH_RATE_WINDOW_SEC = 10.0
BOOK_WATCH_FLAGS_KEEP = 50
BOOK_WATCH_PULLS_KEEP = 50
BOOK_WATCH_READ_LIMIT = 20
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
)
BOOK_WATCH_NOTE = "Hints consistent with spoofing -- never a detection."
