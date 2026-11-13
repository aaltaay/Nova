"""The three lanes' constants (ADR 071). Owner: backend/line_lanes/.

Nothing here places, stages or cancels an order: a lane holds one IBKR Level 2 line and one AllLast line.
"""
from __future__ import annotations

LANES_SCHEMA_VERSION = 1

# How often the bots' lane is chosen again and every lane's lines are asked for again when they are down. A tick
# reads memory only (the setup scanner, the bot session, the focus sensor) and asks IBKR only for a lane's line
# that is not up.
LANES_BOTS_TICK_SEC = 15.0

# Your lane's stock is recorded while you watch it, and this long after (operator, 2026-11-13: "A Trader tab I can
# see" -- it stops 5 minutes after you leave it, so flipping tabs does not cut it into pieces).
LANES_YOU_RECORD_TAIL_SEC = 300.0
# A lane stock whose recording would not start (IBKR refused a line, the recorder refused) is tried again this long
# after, not on every tick: each try opens and lets go of the recorder's hold.
LANES_RECORD_RETRY_SEC = 60.0

# A Time & Sales socket's line IBKR refused or ended comes back by itself (#698, ``tape_heal``): asked again once
# IBKR's 15 s same-instrument rule allows, plus this much after refusals in a row (the last repeats; it never stops
# while a socket watches). A new line stands this long without IBKR ending it before the socket hears it is back --
# IBKR answers a refusal after the request.
LANES_TAPE_HEAL_BACKOFF_SEC = (0.0, 15.0, 45.0, 60.0)
LANES_TAPE_HEAL_CONFIRM_SEC = 2.0
LANES_TAPE_HEAL_POLL_SEC = 1.0
# IBKR's tick-by-tick cap: a refusal with this code is said as the cap.
LANES_TAPE_CAP_CODES = frozenset({10190})

# Why the bots' lane is on a setup, best first: the trade's tape is what the exit trials read; the tape at the
# trigger is what the entry trials and the tape gate read (ADR 041).
WHY_TRADE = "trade"
WHY_NEAR = "near"
WHY_ARMED = "armed"
WHY_ORDER = (WHY_TRADE, WHY_NEAR, WHY_ARMED)
WHY_WORDS = {WHY_TRADE: "in a trade", WHY_NEAR: "near its trigger", WHY_ARMED: "armed"}

# The setups' names in the sentences (stock_read/plan.py's words).
SETUP_WORDS = {"first_pullback": "first pullback", "bull_flag": "bull flag",
               "flat_top_breakout": "flat-top breakout", "flat_top_5m": "5-minute flat top",
               "red_to_green": "red to green", "gap_and_go": "Gap and Go", "pullback_dip": "pullback dip", "abcd": "ABCD"}

# Nova's own trades that keep the bots' lane past the scanner's scoring window.
BOT_TRADE_LIVE_STATES = ("entering", "open", "exiting")


# The words a socket or a request reads when no lane is on its stock.
NO_LANE_WORDS = "No lane is on {symbol}: open it in front to bring your Level 2 here."
YOUR_LANE_WORDS = "Your Level 2 is on {lane} -- open {symbol} in front to bring it here."
LANE_LEFT_WORDS = "Your Level 2 moved to {lane}."
LANE_EMPTIED_WORDS = "No lane is on {symbol} now."
