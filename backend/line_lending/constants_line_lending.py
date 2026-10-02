"""Lending a hidden Trader tab's Level 2 line (ADR 044 decision 6). Owner: backend/line_lending/.

Nothing here places, stages or cancels an order: a loan moves one IBKR depth line
(and the tape line the tape gate reads beside it) from a Trader tab the operator
is not looking at to a setup Nova may buy.
"""
from __future__ import annotations

LINE_LENDING_SCHEMA_VERSION = 1

# bot-session.json, desk-wide (not a venue's dial): lending on or off. A session
# without the key lends (the operator's default, ADR 044 decision 6).
LINE_LENDING_SETTING_KEY = "line_lending"
LINE_LENDING_DEFAULT_ON = True

# How often loans are judged: new ones made, standing ones ended. Faster than
# auto-record's 15 s (LEADERBOARD_AUTO_RECORD_TICK_SEC) on purpose: a setup can go
# from armed to its trigger in seconds, and the tape gate needs a book in its
# window before it (TAPE_GATE_WINDOW_SEC). A tick reads memory only.
LINE_LENDING_TICK_SEC = 5.0
# The lender's sockets close when they read the "lent" frame; the loan waits this
# long for them before it gives up (and the tab reconnects through its poll).
LINE_LENDING_RELEASE_WAIT_SEC = 3.0
LINE_LENDING_RELEASE_POLL_SEC = 0.05
# A tab that came to the front (a recall, or a socket opened in front) is not lent
# again this soon: the focus report can trail the tab by a few seconds, and a line
# that moves back and forth costs IBKR requests for nothing.
LINE_LENDING_FRONT_COOLDOWN_SEC = 30.0
# Ended loans kept for GET /api/ibkr/depth/lines (newest first).
LINE_LENDING_RECENT_KEEP = 20
# A borrower whose AllLast line IBKR refused (or ended) asks again this often, at most this many
# times per loan, once IBKR's 15 s same-instrument rule allows -- the refusal may have been that
# rule, or a tick-by-tick line another holder gave up since.
LINE_LENDING_TAPE_RETRY_SEC = 20.0
LINE_LENDING_TAPE_RETRIES = 3
# A held AllLast line down this long without IBKR's word is said as refused: a reconnect asks
# for every held line again within a few seconds, and that is not a refusal.
LINE_LENDING_TAPE_SAY_AFTER_SEC = 10.0

# A Time & Sales socket's line IBKR refused or ended comes back by itself (#698, ``tape_heal``):
# asked again once IBKR's 15 s same-instrument rule allows, plus this much after refusals in a row
# (the last repeats; it never stops while a socket watches). A new line stands this long without
# IBKR ending it before the socket hears it is back -- IBKR answers a refusal after the request.
LINE_LENDING_TAPE_HEAL_BACKOFF_SEC = (0.0, 15.0, 45.0, 60.0)
LINE_LENDING_TAPE_HEAL_CONFIRM_SEC = 2.0
LINE_LENDING_TAPE_HEAL_POLL_SEC = 1.0
# IBKR's tick-by-tick cap: a refusal with this code makes room before the line is asked again.
LINE_LENDING_TAPE_CAP_CODES = frozenset({10190})

# The bot audit stream (bot/audit.py): every loan's start and end, and the switch.
LINE_LENDING_AUDIT_ACTION = "line_loan"
LINE_LENDING_SWITCH_AUDIT_ACTION = "line_lending"
LINE_LENDING_OUTCOME_LENT = "lent"
LINE_LENDING_OUTCOME_ENDED = "ended"
# The borrower's AllLast line was refused or ended (said once per refusal), and later came up.
LINE_LENDING_OUTCOME_TAPE_REFUSED = "tape_refused"
LINE_LENDING_OUTCOME_TAPE_OPENED = "tape_opened"

# The borrower's AllLast line, on the lines view (``loans[].tape_state``).
TAPE_RECEIVING = "receiving"   # a print arrived on it: the tape gate reads prints
TAPE_WAITING = "waiting"       # it is up, no print yet (a quiet name looks the same)
TAPE_REFUSED = "refused"       # Nova holds none, or IBKR refused or ended it (``tape_error`` says why)

# A loan's states: lent frames sent, the lender's line not yet released; then the borrower holds a line.
LOAN_PENDING = "pending"
LOAN_ACTIVE = "active"

# How a loan ends (the contract's ``end``).
LOAN_END_SETUP = "setup_ended"
LOAN_END_TRADE = "trade_ended"
LOAN_END_RECALLED = "recalled"
LOAN_END_OFF = "lending_off"

# Who holds a line on GET /api/ibkr/depth/lines.
HELD_BY_TAB = "tab"
HELD_BY_RECORD = "record"
HELD_BY_AUTO_RECORD = "auto_record"
HELD_BY_LOAN = "loan"
HELD_BY_REPLAY = "replay"

# Why a setup borrows, best first -- auto-record's tiers (leaderboard/auto_record.py).
WHY_TRADE = "trade"
WHY_NEAR = "near"
WHY_ARMED = "armed"
WHY_ORDER = (WHY_TRADE, WHY_NEAR, WHY_ARMED)
WHY_WORDS = {WHY_TRADE: "in a trade", WHY_NEAR: "near its trigger", WHY_ARMED: "armed"}

# The setups' names in the sentences (stock_read/plan.py's words).
SETUP_WORDS = {"first_pullback": "first pullback", "bull_flag": "bull flag",
               "flat_top_breakout": "flat-top breakout", "red_to_green": "red to green",
               "gap_and_go": "Gap and Go"}

# Nova's own trades that keep a loan standing past the scanner's scoring window.
BOT_TRADE_LIVE_STATES = ("entering", "open", "exiting")

LENDING_OFF_WHY = "line lending was switched off"

# The lent frame's sentence (the desk builds the same words from its own constants).
LENT_TEXT = "Level 2 lent to {symbol}'s {setup} ({why}) -- back when it ends or when you bring this tab to the front"
LENT_TEXT_NO_WHY = "Level 2 lent to {symbol}'s {setup} -- back when it ends or when you bring this tab to the front"
