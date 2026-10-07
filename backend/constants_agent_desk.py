"""Constants for the agent endpoints (ADR 050): find stock-days, show them in the Sim, the dictionary."""
from __future__ import annotations

AGENT_DESK_SCHEMA_VERSION = 1

# ── Search (GET /api/agent/movers) ──────────────────────────────────────────
# "common": these reference types, and a ticker of 1-4 letters the reference has no type for.
AGENT_MOVERS_COMMON_KINDS = ("CS", "ADRC")
AGENT_MOVERS_LIMIT_DEFAULT = 25
AGENT_MOVERS_LIMIT_MAX = 500
# A search matching more stock-days than this answers the count only ("narrow the search").
AGENT_MOVERS_MAX_SCAN = 200_000

# ── Commands the desk runs (show / move) ────────────────────────────────────
# A queued command no main desk window takes within this has expired (the desk is closed or busy).
AGENT_COMMAND_CLAIM_SEC = 15.0
# A command the desk took and stopped reporting on for this long has failed.
AGENT_COMMAND_STALE_SEC = 20 * 60.0
# A command a desk window took but never reported on goes back in the queue after this: the window that asked
# went away (a reload, a closed window) while its poll still waited on the server (found 2026-10-06).
AGENT_COMMAND_FIRST_REPORT_SEC = 10.0
# A command the desk is running and that went this long with no report has failed (its window closed mid-way).
AGENT_COMMAND_LEASE_SEC = 90.0
# Commands remembered for the agents' reads (newest).
AGENT_COMMAND_KEEP = 50
# A desk window that long-polled within this is listening.
AGENT_DESK_LISTEN_SEC = 40.0
# The longest any long poll waits (the desk's own poll waits AGENT_DESK_POLL_WAIT_SEC).
AGENT_LONG_POLL_MAX_SEC = 30.0
AGENT_DESK_POLL_WAIT_SEC = 25.0

# ── Where a show lands ──────────────────────────────────────────────────────
# A run or a drop: the playhead parks this long before it began, paused.
AGENT_PARK_LEAD_SEC = 5 * 60
# The window loaded: the desk's own length (09:15-11:30), from a quarter hour this long before the park, so the
# charts hold half an hour of what came before (a Massive window's candles are its own; measured on AMOD 2026-10-02).
AGENT_WINDOW_MINUTES = 135
AGENT_WINDOW_LEAD_MIN = 30
# Narrower windows, tried in order when a busy window is over the Sim's print or quote cap.
AGENT_FALLBACK_WINDOWS_MIN = (60, 30)
# The anchors a show or a move may name besides an ET time (HH:MM).
AGENT_AT_ANCHORS = ("run", "drop", "high", "low", "open", "premarket")

# ── The dictionary (operator data, in the cache) ────────────────────────────
AGENT_DICTIONARY_FILENAME = "agent-dictionary.json"
AGENT_DICTIONARY_SCHEMA_VERSION = 1
AGENT_DICTIONARY_MAX_ENTRIES = 500
AGENT_DICTIONARY_ID_MAX = 64
