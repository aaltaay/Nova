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
# smaller. Prints this far either side of the two books count toward the drop
# (matching.py). Measured over the 27 Session Records of 2026-09-21..29
# (tools/book_watch_window_study.py): the book does trail the tape -- of the
# lit prints through the displayed best price, 88% saw a book show that level
# gone within 0.5 s and 10% took 0.5-3 s -- but a wider window claims more
# prints that only traded at the same price nearby. Reaching 1 s before the
# earlier book would fill 2.3% of the size now called pulled, only 0.5-0.6
# points of it beyond chance (the same prints moved 30-60 s, or one tick out);
# 3 s, 7.8% with 1.3-2.2 beyond; past the later book, less. Keep 0.5. With the sweep
# rule below (#636) the 1 s reach still adds 2.0%, 0.3-0.4 points beyond chance.
BOOK_WATCH_MATCH_SLACK_SEC = 0.5
# A drop is judged this long after the book that showed it, so a late print
# can still claim it; must exceed the slack. Every ladder mark waits this long.
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
# A Session Record keeps no venue: a row with the price and odd size (not a multiple of this) of a row
# above it, that the book before held fewer of, is IBKR moving one order, shown twice (#1133). On
# 2026-10-21, 431 of 437 such new pairs lasted one book; a round-lot pair is mostly two venues.
BOOK_WATCH_ROUND_LOT = 100

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

# A level a print traded through (matching.Sweeps, #636). A lit, price-setting print above the
# book's best ask (below its best bid) proves the size the book showed at the round-lot levels from
# the best to its own price traded: a protected quote cannot be traded through. IBKR's book can show
# it for seconds more, so for this long after the sweep a drop at one of those levels takes the
# sweep's own prints (0.5 s either side of it) first, at most the size the sweep proved taken; new
# size posted there ends it, since a later drop may be the new order, pulled. The book showed 98% of
# through levels smaller within 3 s. Measured with tools/book_watch_window_study.py on the Session
# Records of 2026-09-21..29: it adds 0.37% of the size called pulled (the drops it covers read 86.2%
# traded without it, 88.7% with it); 98% of that is beyond chance against the level a tick past each
# sweep and 76% against the same sweeps moved 30-60 s -- on the recordings that kept every book
# (09-25, 09-29), 0.14%, 91% and 49%. A first version without the owed size or the end on new size
# added 1.6%, 84% of it at levels refilled after the sweep.
BOOK_WATCH_SWEEP_HOLD_SEC = 3.0
# An odd-lot best price is not a protected quote: a print through it proves nothing.
BOOK_WATCH_SWEEP_MIN_LEVEL = 100
# Prints that prove nothing about the book: crosses, volume-only prints and odd lots.
BOOK_WATCH_SWEEP_SKIP_CONDITIONS = BOOK_WATCH_HIDDEN_SKIP_CONDITIONS | BOOK_WATCH_AUCTION_CONDITIONS | frozenset("I")

# A big seller on the ask, a big buyer on the bid (big_seller.py, #846; operator ask 2026-10-12: the
# operator's material lists "high selling pressure / big sellers on the ask" as a reason to get out).
# CHOSEN, not measured: a description of the book for the trade you hold, never an order or a gate.
# A price is big when its resting size is at least the share floor AND the dollar floor -- a quiet
# book's ordinary 1,000-share order is not a seller anyone waits behind, and on a sub-$2 stock the
# dollars set the floor (20,000 / $1.25 = 16,000 shares) -- AND this many times the median of the other
# levels in view on its side: the book around it, so a busy book's ordinary size is never "big". The
# watcher's large pull is 4x; a size that sits in the way has to stand out more than one that leaves.
BOOK_WATCH_BIG_MIN_SHARES = 10_000
BOOK_WATCH_BIG_MIN_DOLLARS = 20_000.0
BOOK_WATCH_BIG_MEDIAN_MULT = 5.0
# Fewer other levels in view than this and there is no book around it to weigh it against: no call.
BOOK_WATCH_BIG_MIN_OTHER_LEVELS = 3
# At or just over the price (just under, for a bid): no further than the larger of 5 cents and 1% of the
# price, and never more than 3% -- a few cents on a $3 stock, a dime on a $10 one, 3 cents on a $1 one.
# The price is the last print that sets one, else the middle of the inside.
BOOK_WATCH_BIG_WINDOW_DOLLARS = 0.05
BOOK_WATCH_BIG_WINDOW_PCT = 0.01
BOOK_WATCH_BIG_WINDOW_MAX_PCT = 0.03
# Called once it has stayed that big this long: an order posted and pulled within a second or two is
# no seller anyone could count on (IBKR's book arrives in batches a fraction of a second apart).
BOOK_WATCH_BIG_MIN_HOLD_SEC = 3.0
# A called price whose size the book shows fall under the floors left: lit prints at its price inside the
# watcher's matching window (matching.py) covering at least this share of the drop read "taken", else
# "pulled". A lit print through it (over a seller, under a buyer) reads taken at once: a displayed price
# cannot be traded through (the sweep rule, matching.py).
BOOK_WATCH_BIG_TAKEN_SHARE = 0.5
# Ended ones stay in the reading this long, so the held card can say "taken" or "pulled".
BOOK_WATCH_BIG_SHOW_ENDED_SEC = 30.0
# Ended ones kept per line (the journal keeps them all).
BOOK_WATCH_BIG_KEEP = 100
# On a Sim replay (a Session Record at the playhead) the reading runs the same tracker over this much of the
# recorded book and tape before the playhead: a price there longer reads "held 3 min+".
BOOK_WATCH_BIG_REPLAY_LOOKBACK_SEC = 180.0
# A price called where a wall on its side was pulled this recently says it is back, and how often (#984).
BOOK_WATCH_BIG_BACK_SEC = 300.0
# How fast the stock trades, for "40 s of lit volume" (#984): lit shares over this window, odd lots counted.
# Before BOOK_WATCH_BIG_PACE_MIN_SEC of watching there is no pace: a few seconds' prints are no minute's.
BOOK_WATCH_BIG_PACE_SEC = 60.0
BOOK_WATCH_BIG_PACE_MIN_SEC = 10.0
BOOK_WATCH_BIG_NOTE = (
    "Resting size much larger than the book around it, at or just past the price: one order or several at "
    "one price look the same here. A description of the book, shown, never acted on."
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
    f"Filled means lit prints at exactly that price within {BOOK_WATCH_MATCH_SLACK_SEC:g} s of the two books; "
    "off-exchange (FINRA) and midpoint prints never fill a level.",
    f"IBKR's book can trail its tape: a level a print traded through reads traded, up to the size shown there, "
    f"when the book shows it gone within {BOOK_WATCH_SWEEP_HOLD_SEC:g} s of that print with nothing new posted "
    "there first; size that traded at the best with nothing through it, shown gone late, still reads pulled.",
    "Hidden means lit prints at a price that held, beyond the most the book ever showed there; "
    "cross (auction) prints and off-exchange reports never count.",
)
BOOK_WATCH_NOTE = "Hints consistent with spoofing -- never a detection."
