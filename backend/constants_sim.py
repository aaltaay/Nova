"""Local Sim Feed + Sim Fill tunables (weekend practice harness).

Owner: backend/sim/. Not IBKR. Never mixed with Gateway prices or orders.
"""
from __future__ import annotations

import os

# Env selector. "sim" turns on the local practice broker + looping tape.
NOVA_BROKER_ENV = "NOVA_BROKER"
NOVA_BROKER_SIM = "sim"
NOVA_BROKER_IBKR = "ibkr"

SIM_SYMBOL = "SIM1"
SIM_NAME = "Nova Sim Tape"
SIM_EXCHANGE = "SIM"

# Synthetic session around a stable mid so limits can be written by hand.
SIM_PREV_CLOSE = 25.00
SIM_START_LAST = 25.10
SIM_SPREAD = 0.02
SIM_TICK_AMPLITUDE = 0.18
SIM_TICK_STEP_RAD = 0.35
SIM_TICK_INTERVAL_SEC = 0.25
SIM_PRINT_SIZE = 100
SIM_BOOK_LEVELS = 5
SIM_BOOK_SIZE = 200
SIM_BOOK_TICK = 0.01

# Practice ledger -- not real buying power. In-memory only (process start).
SIM_STARTING_CASH = 100_000.0
SIM_STARTING_BUYING_POWER = 200_000.0

SIM_SPEND_STATUS = "sim_armed"
# Effective status when the ADR 018 arm latch is off. Must match the value
# ibkr.safety.spend_state returns so one vocabulary reaches every surface.
SIM_SPEND_LOCKED_DISARMED = "locked_disarmed"
SIM_MODE_LABEL = "sim"
SIM_NO_IBKR_REASON = "SIM mode cannot place to IBKR"
SIM_NO_IBKR_CODE = "SIM_NO_IBKR"

# Chart history seeded from the looping mid so /bars is never a 503.
SIM_CHART_BARS_DEFAULT = 120


def nova_broker_from_env() -> str:
    raw = (os.environ.get(NOVA_BROKER_ENV) or "").strip().lower()
    if raw == NOVA_BROKER_SIM:
        return NOVA_BROKER_SIM
    return NOVA_BROKER_IBKR


def _desk_venue_cache_root() -> str:
    return (
        os.environ.get("NOVA_CACHE_DIR")
        or os.path.join(os.path.dirname(__file__), ".cache")
    )


# Owner: sim/mode.py (the only reader/writer). Invalidation trigger: an
# operator venue click only -- ADR 018 makes the *settled* venue deliberately
# restart-independent, so no session rollover or reconnect generation stales
# it. An in-flight gateway-mode switch is never stored here; that stays in
# ibkr/gateway_heal.py process state (ADR 018 decision 7).
DESK_VENUE_FILE = os.path.join(_desk_venue_cache_root(), "desk-venue.json")
DESK_VENUE_SCHEMA_VERSION = 1

# Session window for looping tape (America/New_York clock).
SIM_SESSION_OPEN_HOUR = 4
SIM_SESSION_CLOSE_HOUR = 20

# Historical replay acquisition (architecture/historical-replay.md).
SIM_HISTORY_DIR_ENV = "NOVA_SIM_HISTORY_DIR"
SIM_HISTORY_DEFAULT_ROOT_WIN = r"F:\Nova\sim\_capture\historical"
SIM_HISTORY_PAGE_SIZE = 1000
SIM_HISTORY_REQUEST_INTERVAL_SEC = 11.0
SIM_HISTORY_RETRY_INTERVAL_SEC = 16.0
SIM_HISTORY_REQUEST_TIMEOUT_SEC = 45.0
SIM_HISTORY_CONNECT_TIMEOUT_SEC = 15.0
SIM_HISTORY_MAX_PAGES = 10000
SIM_HISTORY_CLIENT_ID = 29420
SIM_HISTORY_TAPE_ROWS = 200
SIM_TICK_INTERVAL_RTH_SEC = 0.08
SIM_TICK_INTERVAL_EXT_SEC = 0.15

# Selection and per-selection caches are bounded; downloads themselves are durable.
SIM_HISTORY_MAX_SELECTION_PRINTS = 500_000
SIM_HISTORY_ARCHIVE_CACHE_ENTRIES = 12
SIM_HISTORY_RESULT_CACHE_ENTRIES = 12
SIM_HISTORY_QUOTE_CANDLES = 2000
SIM_HISTORY_SQLITE_TIMEOUT_SEC = 30
SIM_HISTORY_SCHEMA_CACHE_ENTRIES = 32
