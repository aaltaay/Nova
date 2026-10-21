"""The daily loss limit's constants (ADR 056, ADR 061, ``architecture/schema/loss-limit.md``)."""
from __future__ import annotations

LOSS_LIMIT_FILE = "loss-limit.json"                 # the operator's setting, in the operator cache
LOSS_LIMIT_STATE_FILE = "loss-limit-state.json"     # today's warnings and trips per account and line
LOSS_LIMIT_SCHEMA_VERSION = 2                       # ADR 061: version 1 (one line) is read as the Account line
LOSS_LIMIT_STATE_SCHEMA_VERSION = 2                 # ADR 061: version 1's record per account is its Account line

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

# The lines (ADR 061): the Account line counts every trade opened today; the You and Bots lines each
# count one side's. A trade belongs to the side whose order opened its shares.
LOSS_LIMIT_LINE_ACCOUNT = "account"
LOSS_LIMIT_LINE_YOU = "you"
LOSS_LIMIT_LINE_BOTS = "bots"
LOSS_LIMIT_SIDES = (LOSS_LIMIT_LINE_YOU, LOSS_LIMIT_LINE_BOTS)
LOSS_LIMIT_LINES = (LOSS_LIMIT_LINE_ACCOUNT, *LOSS_LIMIT_SIDES)
# Each line's dollars in the setting; null for You or Bots is no line (the Account line is always set).
LOSS_LIMIT_LINE_KEYS = {LOSS_LIMIT_LINE_ACCOUNT: "limit_usd", LOSS_LIMIT_LINE_YOU: "you_usd",
                        LOSS_LIMIT_LINE_BOTS: "bots_usd"}

LOSS_LIMIT_ORIGIN = "loss_limit"                    # the origin on the Account line's Auto sell
# The origin on a side line's Auto sell: the close is stamped with the line that sold, so the count gives
# its shares back to that side (ADR 061), and the Orders table says which line sold.
LOSS_LIMIT_SIDE_ORIGINS = {LOSS_LIMIT_LINE_YOU: "loss_limit_you", LOSS_LIMIT_LINE_BOTS: "loss_limit_bots"}
LOSS_LIMIT_ORIGINS = (LOSS_LIMIT_ORIGIN, *LOSS_LIMIT_SIDE_ORIGINS.values())
# The bots' own closes go out as source ``flatten``; these origins say they are a bot's (ADR 042, ADR 055).
LOSS_LIMIT_BOT_CLOSE_ORIGINS = ("bot", "bot_api", "live_trader")

# Reason codes on the wire.
LOSS_LIMIT_REASON_NO_NEW_BUYS = "LOSS_LIMIT_NO_NEW_BUYS"
LOSS_LIMIT_REASON_INVALID = "LOSS_LIMIT_INVALID"
