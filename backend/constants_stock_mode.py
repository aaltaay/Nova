"""Who trades the stock (ADR 037, ADR 042 F): the per-stock Buy / Sell switch and what Nova does with it.

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
# A trade kind, not a mode: Nova holds the exit of a stock you bought (ADR 037 amendment 2026-10-01).
STOCK_MODE_EXIT = "exit"
STOCK_MODE_MODES = (STOCK_MODE_SIGNAL, STOCK_MODE_APPROVE, STOCK_MODE_AUTO_ENTRY, STOCK_MODE_BOT)
STOCK_MODE_NAMES = {
    STOCK_MODE_SIGNAL: "Signal only",
    STOCK_MODE_APPROVE: "Approve",
    STOCK_MODE_AUTO_ENTRY: "Auto-entry",
    STOCK_MODE_BOT: "Bot",
}

# Every Nova entry rests at most the venue sleeve's ``working_ttl_sec`` unfilled (ADR 042 E), then is
# cancelled (a miss): the bot, Auto-entry and Approve alike.
# The runner's loop, like the bot's.
STOCK_MODE_POLL_SEC = 0.5
# How often a waiting approval is checked against its lane (a re-arm withdraws it).
STOCK_MODE_APPROVAL_CHECK_SEC = 2.0
# Risk per trade the desk may send (mirrors frontend STOCK_READ_RISK_MAX_USD and the sleeve's bounds).
STOCK_MODE_RISK_MIN_USD = 1.0
STOCK_MODE_RISK_MAX_USD = 10_000.0
# An approval binds to the lane's own levels: within a cent.
STOCK_MODE_PRICE_TOLERANCE = 0.01
# Cancels of a sent entry and of the exits are retried after this long when the order still works.
STOCK_MODE_CANCEL_RETRY_SEC = 2.0
STOCK_MODE_SYMBOL_MAX_LEN = 12

# Nova's stock-mode trades survive a restart (ADR 042 F): the operator cache file.
STOCK_MODE_TRADES_FILENAME = "stock-mode-trades.json"
STOCK_MODE_TRADES_SCHEMA_VERSION = 1
STOCK_MODE_TRADES_KEEP_DAYS = 7

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
# ADR 042 F: Approve refuses a setup the template's filter keeps out, and any NOT A TRADE plan.
STOCK_MODE_FILTERED = "STOCK_MODE_FILTERED"
STOCK_MODE_NOT_A_TRADE = "STOCK_MODE_NOT_A_TRADE"
# ADR 049 (#778 step 4): Approve sends a long bracket, so it refuses a short setup until the bot trades both sides.

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
    "You hold {sym}: hand Nova the exit with \"Nova takes the exit\" (\"Nova takes the cover\" on a short) on "
    "the plan box (Paper and Sim), or close it yourself."
)
STOCK_MODE_WHY_LIVE_EXIT = (
    "On Live, Nova never moves a Live order by itself, and a plain IBKR stop does not trigger before 9:30 "
    "(#604). Set your stop and sell it yourself; Nova takes the exit on Paper and Sim."
)

# What keeps Nova from sending although the switch is set (skip codes on the audit stream, and the
# view's ``notes``).
STOCK_MODE_BLOCK_DISARMED = "DESK_DISARMED"
STOCK_MODE_BLOCK_KILL = "KILL_SWITCH"
STOCK_MODE_BLOCK_DAY_LOCK = "BOT_DAY_LOCK"
STOCK_MODE_BLOCK_BOT_TRIP = "BOT_TRIP"
STOCK_MODE_BLOCK_TAPE = "TAPE_NOT_GO"
STOCK_MODE_BLOCK_STALE = "TRIGGER_STALE"
STOCK_MODE_BLOCK_WORKING = "ENTRY_WORKING"
STOCK_MODE_WHY_DISARMED = "The padlock is locked: unlock it so Nova can place orders."
STOCK_MODE_WHY_KILL = "The kill switch is tripped: nothing is sent until you reset it."
STOCK_MODE_WHY_DAY_LOCK = "The all-stop tripped on this venue today: buys here are locked until 04:00 ET."
STOCK_MODE_WHY_BOT_TRIP = ("The bot trip fired on this venue today: Nova buys nothing more here until you "
                           "re-enable the bot (Activate on the Bots page) or 04:00 ET.")
# ADR 049 (#778 step 4): the plan's setup is a short, which no Nova mode trades until step 5 (the view's note).
STOCK_MODE_NOTE_NOT_FOLLOWED = (
    "The setup scanner does not follow {sym} (it follows the HOD Momo names): no setup can trigger here, "
    "so Nova will not act."
)
