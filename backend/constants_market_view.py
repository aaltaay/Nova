"""The real-time view and the order gate (ADR 045). Owner: ``market_view/``.

Measured on 2026-10-05 (APUS, 08:30 ET): the operator's Level 2 showed a book 3-7 s old, the
order reached the backend 2-3 s after the click, and it rested above the market. These bound
how old a view may be before Nova refuses an order priced from it.
"""

MARKET_VIEW_SCHEMA_VERSION = 1

# Versions kept per symbol and stream. A busy name changes its book about 17 times a second,
# so this reaches back about four minutes; a view older than the kept history is stale.
MARKET_VIEW_HISTORY_KEEP = 4096

# With nothing new to send, a Level 2 socket says "still current" this often (a ``beat``).
MARKET_VIEW_BEAT_SEC = 0.25

# The gate (``market_view/gate.py``), in milliseconds.
ORDER_VIEW_MAX_LAG_MS = 500.0   # the screen's book or quote had been replaced this long at the action
ORDER_MAX_ARRIVAL_MS = 500.0    # from the action to the door
ORDER_MAX_SEND_MS = 750.0       # from the action to the broker send
ORDER_MAX_IB_STALL_MS = 500.0   # the IB loop (it applies every market-data message) stuck this long now
ORDER_CLOCK_SKEW_MS = 1000.0    # an action this far in the backend's future: the clocks disagree

VIEW_STALE = "VIEW_STALE"
ORDER_LATE = "ORDER_LATE"
FEED_STALE = "FEED_STALE"
VIEW_MISSING = "VIEW_MISSING"

# Getting flat must always work: these are never refused by the gate.
VIEW_GATE_EXEMPT_TEXT = "Flatten and cancels still work."
