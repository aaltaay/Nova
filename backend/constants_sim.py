"""Sim practice desk tunables: replayed real sessions and a local fill ledger.

Owner: backend/sim/. Not IBKR. Never mixed with Gateway prices or orders.
There is no synthetic instrument: Sim trades a loaded historical download or
recorded capture of a real ticker (#310, #315).
"""
from __future__ import annotations

import os

# Env selector. "sim" starts the process on the local practice desk.
NOVA_BROKER_ENV = "NOVA_BROKER"
NOVA_BROKER_SIM = "sim"
NOVA_BROKER_IBKR = "ibkr"

# Practice orders are refused with one of these codes (architecture/practice-fills.md).
SIM_NO_REPLAY_CODE = "SIM_NO_REPLAY"
SIM_NO_REPLAY_REASON = "Load a recording or a historical window before placing a practice order"
SIM_SYMBOL_MISMATCH_CODE = "SIM_SYMBOL_MISMATCH"
SIM_NO_PRICE_CODE = "SIM_NO_PRICE"
SIM_NO_PRICE_REASON = "No trade has printed yet at the replay playhead"
SIM_NO_TRADES_CODE = "SIM_NO_TRADES"
SIM_NO_TRADES_REASON = (
    "This historical window has candles only; download its trades to practise against it"
)
SIM_ORDER_TYPE_CODE = "SIM_ORDER_TYPE"

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

# Default replay session window (America/New_York clock).
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
# Leading words of the refusal when neither Gateway port answers. The Sim tab
# prompt keys its auto-retry on it (mirrored in frontend simConstants.ts), so
# a Gateway that is simply not running heals on its own once it is back.
SIM_HISTORY_GATEWAY_UNREACHABLE = "IB Gateway unreachable"
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

# Recorded Level 2 inside historical replay (#309, ADR 017). An IBKR historical
# download carries trades only, so depth comes from the local recorder archive
# (backend/l2/) -- a feeder, never a second replay engine or store.
SIM_HISTORY_DEPTH_SOURCE = "l2_recorder"
# A recorded book stands for the playhead only while it is this fresh. The
# continuous depth recorder samples once a second
# (L2_CONTINUOUS_SNAPSHOT_INTERVAL_SEC), so one spare second absorbs a skipped
# sample without letting an old book stand in for an unrecorded stretch.
SIM_HISTORY_DEPTH_MAX_AGE_SEC = 2.0
# Resolved books per replayed second. The snapshot is polled by the Level 2
# panel, the chart and practice admission, so the archive is read at most once
# per second no matter how many callers ask.
SIM_HISTORY_DEPTH_CACHE_ENTRIES = 16
# Per-print sides from the local L2 recording (AGENTS.md §3). Memoized per
# (symbol, second) because the replay tape is re-polled every second.
SIM_HISTORY_SIDE_SOURCE = "recorded_book"
SIM_HISTORY_SIDE_CACHE_ENTRIES = 4096
