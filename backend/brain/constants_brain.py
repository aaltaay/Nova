"""The brain's door (ADR 072 decision 10, amendment 1). Owner: backend/brain/. Shapes: ``bot.md`` "The brain's door"."""
from __future__ import annotations

BRAIN_ORIGIN = "brain"
BRAIN_VENUE = "paper"                 # its Sim door is still to come (the replay clock in the day stop and flat by)
BRAIN_SCHEMA_VERSION = 1              # GET /api/brain
BRAIN_SESSION_HEADER = "X-Nova-Brain-Session"
BRAIN_KEY_PREFIX = "brain:"
BRAIN_SETUP_PREFIX = "brain:"

# The brain's program says it is alive this often or sooner; older than this and its pill says it is not running.
BRAIN_HEARTBEAT_STALE_SEC = 30.0
# Nova's own check of the brain's flat-by time, and of a program that stopped answering.
BRAIN_TICK_SEC = 5.0
# The brain's day stop until its loss line lands (ADR 072 build order 4): its own book's P&L today, as Claude's.
BRAIN_DAY_STOP_USD = -500.0

BRAIN_NOTE_MAX = 280
BRAIN_WHY_MAX = 140
BRAIN_READING_MAX = 8
BRAIN_EVENTS_MAX = 50

# Why the door refuses (409 ``{reason, error}``).
BRAIN_HELD = "BRAIN_HELD"                     # another program holds the door
BRAIN_NOT_CLAIMED = "BRAIN_NOT_CLAIMED"       # a write before its claim
BRAIN_SWITCH_OFF = "BRAIN_SWITCH_OFF"
BRAIN_NOT_PAPER = "BRAIN_NOT_PAPER"
BRAIN_SHAPE = "BRAIN_SHAPE"
BRAIN_PAST_FLAT_BY = "BRAIN_PAST_FLAT_BY"
BRAIN_HALTED = "BRAIN_HALTED"
BRAIN_NO_LINE = "BRAIN_NO_LINE"
BRAIN_IN_TRADE = "BRAIN_IN_TRADE"
BRAIN_DAY_STOP = "BRAIN_DAY_STOP"
BRAIN_STALE = "BRAIN_STALE"
BRAIN_REFUSED = "BRAIN_REFUSED"               # anything else, said in words
BRAIN_HELD_TEXT = "Another program holds the brain's door: its heartbeat is fresh"
BRAIN_NOT_CLAIMED_TEXT = "This program has not claimed the brain's door (POST /api/brain/claim with X-Nova-Brain-Session)"
BRAIN_UNREAD_TEXT = "Paper could not be read just now, so the brain sends nothing: an unknown is never read as flat"

BRAIN_EVENT_KINDS = ("claim", "watch", "armed", "buy_set", "fill", "stop_moved", "close", "refused", "flat_by",
                     "silent", "switch_on", "switch_off", "handed")
