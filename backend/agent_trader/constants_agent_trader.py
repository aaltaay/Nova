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
AGENT_TICK_SEC = 0.5                # reflexes are checked this often (decision 11)

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

# Audit actions (``audit`` stream).
AGENT_AUDIT_ACTION = "agent_trader"
