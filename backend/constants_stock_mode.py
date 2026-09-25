"""Who trades the stock (ADR 037): the per-stock Buy / Sell switch and what Nova does with it.

CHOSEN numbers carry the operator's veto (ADR 037, Consequences).
"""
from __future__ import annotations

STOCK_MODE_SCHEMA_VERSION = 1

# The two sides and the four modes they make.
STOCK_MODE_SIDE_YOU = "you"
STOCK_MODE_SIDE_NOVA = "nova"
STOCK_MODE_SIDES = (STOCK_MODE_SIDE_YOU, STOCK_MODE_SIDE_NOVA)
STOCK_MODE_SIGNAL = "signal"
STOCK_MODE_APPROVE = "approve"
STOCK_MODE_AUTO_ENTRY = "auto_entry"
STOCK_MODE_BOT = "bot"
STOCK_MODE_MODES = (STOCK_MODE_SIGNAL, STOCK_MODE_APPROVE, STOCK_MODE_AUTO_ENTRY, STOCK_MODE_BOT)
STOCK_MODE_NAMES = {
    STOCK_MODE_SIGNAL: "Signal only",
    STOCK_MODE_APPROVE: "Approve",
    STOCK_MODE_AUTO_ENTRY: "Auto-entry",
    STOCK_MODE_BOT: "Bot at Strategy",
}

# CHOSEN: an entry Nova sent that has not filled after this long is cancelled (a miss). The bot's
# sleeve TTL is seconds; a plan the operator sized and approved gets a little longer.
STOCK_MODE_ENTRY_TTL_SEC = 10.0
# The runner's loop, like the bot's.
STOCK_MODE_POLL_SEC = 0.5
# How often a waiting approval is checked against its lane (a re-arm withdraws it).
STOCK_MODE_APPROVAL_CHECK_SEC = 2.0
# Risk per trade the desk may send (mirrors frontend STOCK_READ_RISK_MAX_USD).
STOCK_MODE_RISK_MIN_USD = 1.0
STOCK_MODE_RISK_MAX_USD = 10_000.0
# An approval binds to the lane's own levels: within a cent.
STOCK_MODE_PRICE_TOLERANCE = 0.01
# Cancels of a sent entry and of the exits are retried after this long when the order still works.
STOCK_MODE_CANCEL_RETRY_SEC = 2.0
STOCK_MODE_SYMBOL_MAX_LEN = 12

# The bot audit stream's action for every stock-mode line (ADR 037 decision 12).
STOCK_MODE_AUDIT_ACTION = "stock_mode"

# Trade kinds and states (the view's ``trade``).
STOCK_MODE_TRADE_KINDS = (STOCK_MODE_AUTO_ENTRY, STOCK_MODE_APPROVE, STOCK_MODE_BOT)
STOCK_MODE_TRADE_ENTERING = "entering"
STOCK_MODE_TRADE_HOLDING = "holding"
STOCK_MODE_TRADE_CLOSED = "closed"
STOCK_MODE_TRADE_MISSED = "missed"
STOCK_MODE_TRADE_HANDED = "handed"

# Refusals: {detail: {reason, error, field}}.
STOCK_MODE_INVALID = "STOCK_MODE_INVALID"
STOCK_MODE_RISK = "STOCK_MODE_RISK"
STOCK_MODE_LIVE = "STOCK_MODE_LIVE"
STOCK_MODE_REPLAY = "STOCK_MODE_REPLAY"
STOCK_MODE_HELD = "STOCK_MODE_HELD"
STOCK_MODE_NOT_APPROVE = "STOCK_MODE_NOT_APPROVE"
STOCK_MODE_PLAN_CHANGED = "STOCK_MODE_PLAN_CHANGED"
STOCK_MODE_NOTHING_HELD = "STOCK_MODE_NOTHING_HELD"
STOCK_MODE_BOT_EXITING = "STOCK_MODE_BOT_EXITING"
STOCK_MODE_SEND = "STOCK_MODE_SEND"

# Why a side is locked (``locks``), in the operator's words.
STOCK_MODE_WHY_LIVE_BUY = (
    "On Live, Nova never buys by itself. Paper and Sim come first; Live follows only after Paper "
    "proves it and you decide (#606)."
)
STOCK_MODE_WHY_LIVE_SELL = (
    "Approve on Live waits on your answer to #604 (how the stop protects before 9:30). "
    "Paper and Sim first."
)
STOCK_MODE_WHY_VENUE_UNKNOWN = "Nova cannot read the desk's venue, so it counts as Live: Nova places nothing."
STOCK_MODE_WHY_REPLAY = "Off the live edge the desk is a replay: Nova trades live triggers only."
STOCK_MODE_WHY_HELD = (
    "You hold {sym}: Nova exits only a trade it entered or you approved. Sell it yourself, or flatten first."
)

# What keeps Nova from sending although the switch is set (skip codes on the audit stream, and the
# view's ``notes``).
STOCK_MODE_BLOCK_DISARMED = "DESK_DISARMED"
STOCK_MODE_BLOCK_KILL = "KILL_SWITCH"
STOCK_MODE_BLOCK_DAY_LOCK = "BOT_DAY_LOCK"
STOCK_MODE_BLOCK_BOT_TRIP = "BOT_TRIP"
STOCK_MODE_BLOCK_TAPE = "TAPE_NOT_GO"
STOCK_MODE_BLOCK_STALE = "TRIGGER_STALE"
STOCK_MODE_BLOCK_ENTRY_USED = "ENTRY_USED"
STOCK_MODE_BLOCK_WORKING = "ENTRY_WORKING"
STOCK_MODE_BLOCK_SIZE = "SIZE_ZERO"
STOCK_MODE_WHY_DISARMED = "The padlock is locked: unlock it so Nova can place orders."
STOCK_MODE_WHY_KILL = "The kill switch is tripped: nothing is sent until you reset it."
STOCK_MODE_WHY_DAY_LOCK = "The all-stop tripped today: buys are locked until midnight."
STOCK_MODE_WHY_BOT_TRIP = "The bot trip fired today: Nova buys nothing more today."
STOCK_MODE_NOTE_NOT_FOLLOWED = (
    "The setup scanner does not follow {sym} (it follows the HOD Momo names): no setup can trigger here, "
    "so Nova will not act."
)
STOCK_MODE_NOTE_ENTRY_USED = "Nova's one buy of {sym} today is used."
