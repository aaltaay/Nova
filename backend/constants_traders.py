"""The AI traders' switches, handovers and limits (ADR 072, ``architecture/schema/traders.md``)."""
from __future__ import annotations

TRADER_SWITCHES_FILE = "trader-switches.json"
TRADER_SWITCHES_SCHEMA_VERSION = 1
TRADER_HANDED_FILE = "trader-handed.json"
TRADER_HANDED_SCHEMA_VERSION = 1
TRADER_LIMITS_FILE = "trader-limits.json"
TRADER_LIMITS_SCHEMA_VERSION = 1
TRADERS_SCHEMA_VERSION = 1            # GET /api/traders

# Each AI trader's limits until the operator sets its column in Settings: Claude's code values before ADR 072.
TRADER_DEFAULT_MAX_SHARES = 1_000
TRADER_DEFAULT_RISK_USD = 150
TRADER_DEFAULT_BUDGET_USD = 25_000
TRADER_DEFAULT_FLAT_BY = "15:55"

# Why On is refused (409 ``{reason, error}``).
TRADER_LIVE = "TRADER_LIVE"
TRADER_DAY_STOP = "TRADER_DAY_STOP"
TRADER_PAST_FLAT_BY = "TRADER_PAST_FLAT_BY"
TRADER_OPERATOR_ONLY = "TRADER_OPERATOR_ONLY"
TRADER_UNKNOWN = "TRADER_UNKNOWN"
# The door refuses an AI trader's new order while its switch is Off.
TRADER_OFF = "TRADER_OFF"

# The one venue an AI trader opens trades on. While its switch is On and the desk shows another venue it is paused
# (``traders.pause``, ADR 072 Amendments 3 and 4); ``TRADER_PAUSED`` is that reason, and the cancel code of an
# unfilled entry Nova cancels when the desk leaves this venue.
TRADER_VENUE = "paper"
TRADER_PAUSED = "TRADER_PAUSED"

# The traders that turn themselves On each trading morning (ADR 072 Amendment 2), each with the ``.env`` name
# that, set to 0, leaves its switch to the operator's press alone. ``by`` on a switch the schedule set.
TRADER_WAKES_ENV = {"brain": "NOVA_BRAIN_WAKES"}
TRADER_SWITCH_BY_SCHEDULE = "schedule"

# The trader's one state on its pill.
TRADER_STATE_OFF = "off"
TRADER_STATE_WATCHING = "watching"
TRADER_STATE_BUY_SET = "buy_set"
TRADER_STATE_IN_TRADE = "in_trade"
TRADER_STATE_DONE = "done"
