"""Claude's seat (ADR 068): its sends, its limits and its clocks. Owner: backend/agent_trader/."""
from __future__ import annotations

AGENT_SCHEMA_VERSION = 1

# Every send is the Live Trader bot's shape (ADR 055): entries source ``bot``, closes ``flatten``, cancels
# ``cancel_working``, all with this origin, on Paper only.
AGENT_ORIGIN = "claude"
AGENT_VENUE = "paper"
AGENT_SETUP_PREFIX = "claude:"
AGENT_KEY_PREFIX = "claude:"
AGENT_NAME = "Claude"

# backend/.cache/agent-seat.json: the seat, its lease, its armed breaks, its note and recent events.
AGENT_SEAT_FILE = "agent-seat.json"
AGENT_EVENTS_KEEP = 40

# The lease: a holder that has not checked in for this long has gone quiet (decision 9).
AGENT_LEASE_SEC = 600.0
AGENT_TICK_SEC = 0.5                # reflexes are checked this often (decision 11) ...
AGENT_WAKE_MIN_SEC = 0.1            # ... and on each print or book of a watched stock, this far apart at most (decision 15)
AGENT_WAKE_RING_SEC = 60.0          # the live prints kept per watched stock (>= the reflexes' and guard's look-back)

# A hidden Trader tab's line (decision 14): looked for at most this often while the seat waits; the tab's words
# ("watching RUNR", "in a trade on RUNR") brought up to date this often; after the operator takes a tab's line
# back, the seat asks for no line this long, so the tab reconnects onto the line it was given back.
AGENT_TAB_LINE_TRY_SEC = 2.0
AGENT_TAB_TIER_SEC = 2.0
AGENT_TAB_LINE_HOLD_SEC = 10.0

# The seat's states, as the desk shows them.
SEAT_OFF = "off"                  # nobody holds the seat
SEAT_WAITING = "waiting_line"     # on, no Level 2 line free yet
SEAT_WATCHING = "watching"        # on, holding its line, no order, no shares
SEAT_SET = "buy_set"              # a break or a buy is resting
SEAT_IN = "in_trade"              # holds shares
SEAT_YIELDED = "yielded"          # the operator took the line: no new trades
SEAT_DONE = "done"                # the day's loss stop is reached (or a trade count, when one is set)
SEAT_IDLE = "idle"                # on, no stock chosen yet

# Claude's own limits (the operator's yes, 2026-10-26). Checked before the door; the door's gates still apply.
AGENT_MAX_SHARES = 1000
AGENT_MAX_RISK_USD = 150.0
# No daily trade count (operator, 2026-10-27: "u have infinite trades so we LEARN!"). An int caps it again.
AGENT_MAX_ENTRIES_A_DAY: int | None = None
AGENT_DAY_STOP_USD = -500.0         # Claude's lane: its own daily max loss (operator, 2026-10-26)
AGENT_ENTRY_START_ET = (7, 0)
AGENT_ENTRY_END_ET = (15, 30)
AGENT_CLOSE_ET = (15, 55)          # Nova sells Claude's shares (the day cover's time, ADR 048)
AGENT_OFF_ET = (16, 0)             # the seat turns off
AGENT_BREAK_DEFAULT_MIN = 30.0     # a break that has not triggered expires
AGENT_BREAK_MAX_MIN = 240.0
AGENT_NOTE_MAX_CHARS = 400
AGENT_REFLEX_DEFAULT_MIN = 60.0
AGENT_REFLEX_MAX_MIN = 390.0
AGENT_REFLEX_MAX = 6

# The eye (decision 12): every symbol the scanner follows, over the Level 1 samples ``hod_momo_metrics`` keeps.
AGENT_EYE_WINDOWS_SEC = (10, 30, 60)
AGENT_EYE_SPIKE_SECONDS = 60          # a spike: this window moved ...
AGENT_EYE_SPIKE_MOVE_PCT = 2.0        # ... this many percent or more, either way ...
AGENT_EYE_SPIKE_MIN_DOLLARS = 50_000.0  # ... with at least this much traded in it (operator ask, 2026-10-27)
AGENT_EYE_SCAN_SEC = 1.0              # the watcher scans this often while the seat is on
AGENT_EYE_EVENTS_KEEP = 50
AGENT_EYE_EVENTS_MAX_AGE_SEC = 1800.0
AGENT_EYE_WAIT_MAX_SEC = 30.0         # the longest ``?wait=`` long-poll

# The in-trade guard (decision 13): while Claude holds shares, Nova sells them the moment one of these holds
# (operator, 2026-10-27, from the AIOK prototype that closed at -$40 against -$140 at the hard stop).
AGENT_GUARD_SELLERS_SECONDS = 5.0       # 1. sellers lead: in the last 5 s ...
AGENT_GUARD_SELLERS_RATIO = 2.0         # ... at least 2x what lifted the ask ...
AGENT_GUARD_SELLERS_MIN_SHARES = 1500.0  # ... and at least 1,500 shares at the bid
AGENT_GUARD_BID_LEVELS = 5              # 2. the top 5 bid prices ...
AGENT_GUARD_BID_STACK_FRACTION = 1.0 / 3.0  # ... fall under a third of their size at entry
AGENT_GUARD_BID_UNDER_ENTRY_PCT = 0.4   # 3. the best bid 0.4% or more under Claude's entry
AGENT_GUARD_RETRY_SEC = 5.0             # a close the door refused is tried again after this

# The pop exit (decision 13): half sold at the first pop, then the stop to entry.
EXIT_POP = "pop"
AGENT_POP_PCT_DEFAULT = 1.5             # the first half's target over entry ("about +1.5-2%")
AGENT_POP_PCT_MIN = 0.5
AGENT_POP_PCT_MAX = 5.0
AGENT_GUARD_STALL_AFTER_PCT = 1.0       # the first stall: once the price reached +1% over entry ...
AGENT_GUARD_STALL_SEC = 30.0            # ... no new high for 30 s moves the stop to entry

# The trade journal (decision 16): backend/.cache/agent-journal/<YYYY-MM-DD>.json.
AGENT_JOURNAL_DIR = "agent-journal"
AGENT_JOURNAL_BOOK_ROWS = 10        # the book's top rows each side at entry and exit
AGENT_JOURNAL_PRINTS_SEC = 30.0     # the prints of the last 30 s ...
AGENT_JOURNAL_PRINTS_MAX = 100      # ... newest 100 at most

# Entry kinds (decision 8).
ENTRY_LIMIT = "limit"
ENTRY_BREAK = "break"

# Reason codes on the wire.
AGENT_SEAT_TAKEN = "AGENT_SEAT_TAKEN"
AGENT_NOT_HOLDER = "AGENT_NOT_HOLDER"
AGENT_SEAT_OFF = "AGENT_SEAT_OFF"
AGENT_YIELDED = "AGENT_YIELDED"
AGENT_LIMIT = "AGENT_LIMIT"
AGENT_NOT_PAPER = "AGENT_NOT_PAPER"
AGENT_NO_LINE = "AGENT_NO_LINE"
AGENT_NOT_MINE = "AGENT_NOT_MINE"
AGENT_STALE = "AGENT_STALE"
AGENT_REFUSED = "AGENT_REFUSED"
AGENT_HALTED = "AGENT_HALTED"      # the stock is halted (decision 17)
AGENT_LULD_WARN_PCT = 1.0          # a buy this close to the upper LULD band, or over it, is warned (never refused)

# Audit actions (``audit`` stream).
AGENT_AUDIT_ACTION = "agent_trader"
