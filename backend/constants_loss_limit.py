"""The daily loss limit's constants (ADR 056, ``architecture/schema/loss-limit.md``)."""
from __future__ import annotations

LOSS_LIMIT_FILE = "loss-limit.json"                 # the operator's setting, in the operator cache
LOSS_LIMIT_STATE_FILE = "loss-limit-state.json"     # today's warnings and trips per account
LOSS_LIMIT_SCHEMA_VERSION = 1
LOSS_LIMIT_STATE_SCHEMA_VERSION = 1

LOSS_LIMIT_DEFAULT_USD = 2000                       # whole dollars
LOSS_LIMIT_MIN_USD = 10
LOSS_LIMIT_MAX_USD = 1_000_000
LOSS_LIMIT_DEFAULT_WARN = True
LOSS_LIMIT_DEFAULT_NO_NEW_BUYS = True
LOSS_LIMIT_DEFAULT_AUTO_SELL = False

LOSS_LIMIT_WARN_FRACTION = 0.8                      # Warn me speaks at 80% of the limit
LOSS_LIMIT_CONFIRM_SEC = 10.0                       # the loss stays past a line this long before anything happens
LOSS_LIMIT_POLL_SEC = 1.0
LOSS_LIMIT_SELL_RETRIES = 3

LOSS_LIMIT_ACCOUNTS = ("live", "paper", "sim")
LOSS_LIMIT_ORIGIN = "loss_limit"                    # the origin on Auto sell's closes

# Reason codes on the wire.
LOSS_LIMIT_REASON_NO_NEW_BUYS = "LOSS_LIMIT_NO_NEW_BUYS"
LOSS_LIMIT_REASON_INVALID = "LOSS_LIMIT_INVALID"
