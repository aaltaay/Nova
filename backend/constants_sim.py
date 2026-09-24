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


# ADR 020: the desk venue is live | paper | sim. "live" is the IBKR door (real
# money through the live Gateway, port 4001), "paper" is Nova's practice
# account on the live feed, "sim" is the replay playground. These are the
# values desk-venue.json, /api/desk/venue and /api/ibkr/status carry.
DESK_VENUE_LIVE = "live"
DESK_VENUE_PAPER = "paper"
DESK_VENUE_SIM = "sim"
DESK_VENUES = (DESK_VENUE_LIVE, DESK_VENUE_PAPER, DESK_VENUE_SIM)
# The venues the practice broker (backend/practice/) serves.
DESK_PRACTICE_VENUES = (DESK_VENUE_PAPER, DESK_VENUE_SIM)
PAPER_MODE_LABEL = DESK_VENUE_PAPER
# Effective spend status on the Paper venue while the ADR 018 latch is armed.
# Shares the vocabulary ibkr.safety uses for the legacy IBKR paper door so one
# word reaches every surface; the disarmed value is SIM_SPEND_LOCKED_DISARMED.
PAPER_SPEND_STATUS = "paper_armed"
DESK_PAPER_NO_IBKR_REASON = (
    "Paper venue never places to IBKR -- practice orders fill locally against the live feed"
)


def nova_broker_from_env() -> str:
    raw = (os.environ.get(NOVA_BROKER_ENV) or "").strip().lower()
    if raw == NOVA_BROKER_SIM:
        return NOVA_BROKER_SIM
    return NOVA_BROKER_IBKR


def desk_venue_from_env() -> str:
    """The ``NOVA_BROKER`` bootstrap venue: ``sim`` / ``paper`` / ``live``.

    ``sim`` is unchanged from ADR 018. ``ibkr`` and an unset variable mean the
    IBKR door, which is the Live venue -- exactly what a process with no cache
    file started on before ADR 020, so no existing gate moves.
    """
    raw = (os.environ.get(NOVA_BROKER_ENV) or "").strip().lower()
    if raw in DESK_VENUES:
        return raw
    return DESK_VENUE_LIVE


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
# v2 (ADR 020): {"schema_version": 2, "venue": "live" | "paper" | "sim"}.
DESK_VENUE_SCHEMA_VERSION = 2
# v1 (ADR 018) stored {"venue": "sim" | "ibkr"}. "ibkr" meant the IBKR door
# with whichever Gateway was connected -- in practice the paper one -- so it
# migrates to Paper, the safe direction; Live is always an explicit click. A
# v1 file is rewritten as v2 on first read; any other version refuses loud.
DESK_VENUE_LEGACY_SCHEMA_VERSION = 1
DESK_VENUE_V1_MIGRATION = {NOVA_BROKER_SIM: DESK_VENUE_SIM, NOVA_BROKER_IBKR: DESK_VENUE_PAPER}

# Default replay session window (America/New_York clock).
SIM_SESSION_OPEN_HOUR = 4
# POST /api/sim/clock {session_date} parks a moved-to day here, paused (ADR 023):
# the first pullback's window opens at 07:00 ET.
SIM_DAY_JUMP_PARK_MIN_ET = 7 * 60
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
# A second Nova backend on the same Gateway (a test desk) must not share the
# download client id -- IB answers the later connect with Error 326.
SIM_HISTORY_CLIENT_ID_ENV = "NOVA_SIM_HISTORY_CLIENT_ID"
# Leading words of the refusal when neither Gateway port answers. The Sim tab
# prompt keys its auto-retry on it (mirrored in frontend simConstants.ts), so
# a Gateway that is simply not running heals on its own once it is back.
SIM_HISTORY_GATEWAY_UNREACHABLE = "IB Gateway unreachable"
# Leading words when Gateway accepted the connection but IBKR never answered a
# request within SIM_HISTORY_REQUEST_TIMEOUT_SEC (Gateway logged out, awaiting
# 2FA, or IBKR maintenance). Mirrored in frontend simConstants.ts: the Sim tab
# retries these on a slow timer and offers a Gateway reconnect.
SIM_HISTORY_GATEWAY_NOT_ANSWERING = "IBKR did not answer"
# A download also stores IBKR's regular-hours daily close of the session before
# its day (#542): daily TRADES bars with useRTH over this span ending at that
# day's midnight ET -- a week reaches the prior session across any holiday.
SIM_HISTORY_PRIOR_CLOSE_DURATION = "1 W"
SIM_HISTORY_PRIOR_CLOSE_SOURCE = "ibkr_rth_daily"
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

# --- QA batch fix/qa-sim-replay (2026-09-22) -----------------------------------
# A capture playhead inside a gap in the recording has no market (R11): a
# practice order is refused ``SIM_NO_PRICE`` with this reason, never filled at
# the book or tape from before the gap.
SIM_NOT_RECORDED_REASON = "Not recorded at the replay playhead -- scrub into a recorded stretch to practise"

# --- QA batch fix/qa2-account-practice-sim (2026-09-22) ------------------------
# A historical playhead in a stretch the download has not covered has no print
# (R34): a practice order is refused ``SIM_NO_PRICE`` with this reason instead of
# filling at a 1-minute candle close labelled ``last_print``. A protective close
# still gets flat at the last mark (``last_mark``), as on any unpriced symbol.
SIM_NOT_DOWNLOADED_REASON = (
    "Not downloaded at the replay playhead -- scrub into a downloaded stretch "
    "(or let the download reach it) to practise"
)
# The historical quote card's session figures (W7): the regular session opens at
# 09:30 ET (the Gap% open); the day's volume / high / low count from 04:00 ET.
SIM_HISTORY_SESSION_OPEN_HHMM = (9, 30)
SIM_HISTORY_SESSION_START_HHMM = (4, 0)
