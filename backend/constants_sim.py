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

# Session window for looping tape (America/New_York clock).
SIM_SESSION_OPEN_HOUR = 6
SIM_SESSION_CLOSE_HOUR = 18
SIM_TICK_INTERVAL_RTH_SEC = 0.08
SIM_TICK_INTERVAL_EXT_SEC = 0.15
