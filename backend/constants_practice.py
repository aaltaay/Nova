"""Practice-account tunables for the Paper and Sim venues (ADR 020).

Owner: backend/practice/ (ledger + broker). Never IBKR. Nova's own fake-money
account trades the live feed (Paper) or a loaded replay (Sim); the fill, fee
and margin conventions below are the ones the surveyed simulators agree on,
written down with their sources in ``architecture/practice-account.md``.
Nothing here is invented -- a value without a named source does not belong.
"""
from __future__ import annotations

from constants_ibkr import IBKR_ORDER_TIF_DEFAULT, IBKR_ORDER_TIFS
from constants_sim import SIM_SESSION_CLOSE_HOUR, SIM_STARTING_CASH

# ---------------------------------------------------------------------------
# Account identity
# ---------------------------------------------------------------------------
# Practice account ids stand in for IBKR's DU.../U... ids on /api/ibkr/status
# so the header can always state what the desk is logged into (ADR 020 §3).
PRACTICE_ACCOUNT_ID_PAPER = "NOVA-PAPER"
PRACTICE_ACCOUNT_ID_SIM = "NOVA-SIM"

# ---------------------------------------------------------------------------
# Starting cash
# ---------------------------------------------------------------------------
# Same figure the in-memory Sim ledger has used since ADR 019
# (constants_sim.SIM_STARTING_CASH). IBKR's own paper account seeds USD
# 1,000,000 and Alpaca's USD 100,000; 100k keeps the Paper P&L readable
# against a retail-sized live account. Operator-resettable via
# POST /api/practice/reset {starting_cash}.
PRACTICE_STARTING_CASH = float(SIM_STARTING_CASH)  # 100_000.0

# ---------------------------------------------------------------------------
# Commission -- IBKR Pro, US stocks, FIXED pricing
# https://www.interactivebrokers.com/en/pricing/commissions-stocks.php
# ---------------------------------------------------------------------------
# USD 0.005 per share ...
PRACTICE_COMMISSION_PER_SHARE = 0.005
# ... never less than USD 1.00 per order ...
PRACTICE_COMMISSION_MIN = 1.00
# ... and never more than 1.0 % of trade value (IBKR's published cap; the
# QuantConnect InteractiveBrokersFeeModel carries 0.5 % -- Nova follows IBKR's
# own page, not the port).
PRACTICE_COMMISSION_MAX_PCT = 0.01

# ---------------------------------------------------------------------------
# Regulatory fees -- charged on SELLS only, passed through at cost
# ---------------------------------------------------------------------------
# SEC Section 31 transaction fee, fiscal 2026: USD 20.60 per USD 1,000,000 of
# sale proceeds, effective 2026-04-04
# (https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2).
PRACTICE_SEC_FEE_RATE = 20.60 / 1_000_000  # 0.0000206 of sale value
# FINRA Trading Activity Fee, covered equity securities, effective 2026-01-01:
# USD 0.000195 per share sold, capped at USD 9.79 per trade
# (https://www.finra.org/rules-guidance/guidance/trading-activity-fee).
PRACTICE_FINRA_TAF_PER_SHARE = 0.000195
PRACTICE_FINRA_TAF_MAX = 9.79

# ---------------------------------------------------------------------------
# Buying power -- Regulation T margin account, enforced
# ---------------------------------------------------------------------------
# FINRA Rule 4210 intraday margin, effective 2026-06-04 (Regulatory Notice
# 26-10, https://www.finra.org/rules-guidance/notices/26-10): the pattern day
# trader designation, its USD 25,000 minimum and 4x day-trading buying power
# are gone; equity must cover the maintenance margin of the positions held at
# any moment of the day. FINRA's maintenance margin on long stock is 25 %, so
# intraday buying power is 4x equity. Applied as equity * mult.
PRACTICE_MARGIN_INTRADAY_MULT = 4.0
# FINRA 4210(b)(2): no credit below USD 2,000 of equity -- IBKR keeps this
# Reg T minimum for margin and short sales under the new rule.
PRACTICE_MARGIN_MIN_EQUITY = 2_000.0
# Below the minimum the account buys with its own cash only: equity * 1 less
# gross position value is the cash on hand.
PRACTICE_CASH_MULT = 1.0

# ---------------------------------------------------------------------------
# Live reference freshness (Paper venue)
# ---------------------------------------------------------------------------
# An L1 last older than this is not a price a fill may be estimated from; the
# broker then wants a tape print or refuses (PRACTICE_NO_LIVE_PRINT). Alpaca
# and IBKR paper both fill from the *current* quote and hold when the opposite
# side is absent -- Nova states the absence instead of holding silently.
PRACTICE_LIVE_FRESH_SEC = 15.0

# ---------------------------------------------------------------------------
# Day P&L rollover
# ---------------------------------------------------------------------------
# Day P&L, commissions_today and fills_today reset at 04:00 America/New_York,
# the pre-market open Nova already uses for the Sim session window
# (constants_sim.SIM_SESSION_OPEN_HOUR). IBKR resets its daily figures at the
# same session boundary rather than at midnight.
PRACTICE_DAY_ROLLOVER_HOUR_ET = 4

# ---------------------------------------------------------------------------
# Venue labels, ledger persistence and the Paper matcher cadence
# ---------------------------------------------------------------------------
# ADR 020: the desk venue is live | paper | sim; the practice broker serves
# the last two. "sim" equals constants_sim.SIM_MODE_LABEL so one vocabulary
# reaches every surface.
PRACTICE_VENUE_PAPER = "paper"
PRACTICE_VENUE_SIM = "sim"
# ``AccountType`` on the /api/ibkr/account shape (IBKR sends "INDIVIDUAL";
# the Sim ledger has answered "SIM" since ADR 019).
PRACTICE_ACCOUNT_TYPE_PAPER = "PAPER"
PRACTICE_ACCOUNT_TYPE_SIM = "SIM"
# Paper ledger file under the operator cache (owner: practice/ledger.py via
# practice/persist.py; persisted-state.mdc: schema_version, refuse unknown
# versions loud). A reset archives the old file as
# ``practice-paper-<YYYYMMDD-HHMMSS>.json`` next to it, never deletes it.
PRACTICE_LEDGER_SCHEMA_VERSION = 1
PRACTICE_PAPER_LEDGER_FILE = "practice-paper.json"
PRACTICE_PAPER_ARCHIVE_STAMP = "%Y%m%d-%H%M%S"
# Resting Paper orders are matched against the live tape once a second --
# the same cadence the Sim feed uses for replay prints.
PRACTICE_MATCHER_INTERVAL_SEC = 1.0

# ---------------------------------------------------------------------------
# Ledger history (GET /api/practice/history, the Account page)
# ---------------------------------------------------------------------------
# The ranges are the Account page's tabs, Webull's set less the ones a
# practice ledger opened days ago cannot fill (6M, 1Y). A range starts at the
# practice-day start (PRACTICE_DAY_ROLLOVER_HOUR_ET) that many *calendar* days
# before today's -- a weekend inside the window simply holds no session --
# YTD at Jan 1 of the practice day's year, ALL at the ledger's open. Today is
# the venue's clock: the playhead on Sim. Owner: practice/history.py.
PRACTICE_HISTORY_SCHEMA_VERSION = 1
PRACTICE_HISTORY_RANGE_DEFAULT = "1D"
PRACTICE_HISTORY_RANGE_YTD = "YTD"
PRACTICE_HISTORY_RANGE_ALL = "ALL"
PRACTICE_HISTORY_RANGE_DAYS = {"1D": 1, "5D": 5, "1M": 30, "3M": 90}
PRACTICE_HISTORY_RANGES = (
    *PRACTICE_HISTORY_RANGE_DAYS, PRACTICE_HISTORY_RANGE_YTD, PRACTICE_HISTORY_RANGE_ALL,
)

# ---------------------------------------------------------------------------
# Refusal codes (architecture/practice-fills.md, ADR 020 contract)
# ---------------------------------------------------------------------------
PRACTICE_NO_LIVE_PRINT_CODE = "PRACTICE_NO_LIVE_PRINT"
PRACTICE_NO_LIVE_PRINT_REASON = (
    "No fresh live last and no recent tape print for this symbol -- "
    "a practice fill is never a guess"
)
PRACTICE_BUYING_POWER_CODE = "PRACTICE_BUYING_POWER"
PRACTICE_BUYING_POWER_REASON = (
    "Order cost exceeds the practice account's buying power"
)

# ---------------------------------------------------------------------------
# Time-in-force (operator decision, 2026-09-21)
# ---------------------------------------------------------------------------
# The practice venues honour the two TIFs the execution command carries (#91,
# constants_ibkr.IBKR_ORDER_TIFS): DAY, the default, and GTC. A DAY order
# expires at the close of its session -- the desk's session window ends at
# constants_sim.SIM_SESSION_CLOSE_HOUR (20:00 ET) on Paper; on Sim it is the
# replayed session's close, whatever window the operator loaded -- as a ledger
# event whose row reads ``Expired``. A DAY order placed at or after the close
# works the next session, IBKR's own rule for an after-close DAY order. GTC
# carries no expiry and persists across days and restarts (the Paper ledger
# already does).
PRACTICE_TIF_DAY = IBKR_ORDER_TIF_DEFAULT  # "DAY"
PRACTICE_TIF_GTC = "GTC"
PRACTICE_TIFS = IBKR_ORDER_TIFS
PRACTICE_SESSION_CLOSE_HOUR_ET = SIM_SESSION_CLOSE_HOUR  # 20
PRACTICE_ORDER_STATUS_EXPIRED = "Expired"
PRACTICE_TIF_EXPIRED_CODE = "PRACTICE_TIF_EXPIRED"
PRACTICE_TIF_EXPIRED_REASON = "DAY order expired at the session close"
# A TIF outside PRACTICE_TIFS is refused with the execution door's own code so
# one word reaches the blotter whichever gate caught it (execution/validate.py).
PRACTICE_TIF_INVALID_CODE = "TIF_INVALID"

# ---------------------------------------------------------------------------
# No shorts (operator decision, 2026-09-21)
# ---------------------------------------------------------------------------
# A SELL on a practice venue is only ever risk-reducing, exactly as Invariant
# #7 keeps it on Live: a SELL for more than the held quantity, or any order
# carrying ``short_entry``, is an opening short and is refused at admission
# (execution/practice_checks.py) and again in the broker (practice/broker.py).
PRACTICE_NO_SHORTS_CODE = "PRACTICE_NO_SHORTS"
PRACTICE_NO_SHORTS_REASON = "Nova does not support short entries yet"

# ---------------------------------------------------------------------------
# Brackets (#606 step 1): the order shape Live sends, filled by the practice broker
# ---------------------------------------------------------------------------
# Live sends IBKR's bracket (ibkr/orders.place_bracket_order -> ib_async
# bracketOrder): a LMT entry, a take-profit LMT and a stop-loss STP on the
# reverse side, one quantity, TIF and outside-RTH flag on all three, three
# consecutive order ids, the exits carrying parentId. IBKR holds the exits until
# the entry fills and treats them as one-cancels-other. Paper and Sim take the
# same shape (practice/bracket.py) so Paper rehearses what Live sends.
# ``leg_role`` on a practice row; a plain order carries None.
PRACTICE_LEG_PARENT = "parent"
PRACTICE_LEG_TARGET = "target"
PRACTICE_LEG_STOP = "stop"
# An exit waits for its entry in IBKR's own word for an order that is held,
# not yet working; the entry's fill makes it "Submitted".
PRACTICE_ORDER_STATUS_WAITING = "PreSubmitted"
PRACTICE_ORDER_STATUS_WORKING = "Submitted"
# The exits share one group, "oca-<entry order id>".
PRACTICE_OCA_GROUP_PREFIX = "oca-"
# One exit filled, so the venue cancelled the other (one-cancels-other).
PRACTICE_OCO_CANCELLED_CODE = "PRACTICE_OCO_CANCELLED"
PRACTICE_OCO_CANCELLED_REASONS = {
    PRACTICE_LEG_TARGET: "One-cancels-other: the target filled",
    PRACTICE_LEG_STOP: "One-cancels-other: the stop filled",
}
PRACTICE_OCO_CANCELLED_REASON_DEFAULT = "One-cancels-other: the other exit filled"
# The entry closed unfilled -- cancelled by the operator, refused by the venue at
# the fill, or expired -- so the venue cancelled the exits that waited on it.
PRACTICE_PARENT_CANCELLED_CODE = "PRACTICE_PARENT_CANCELLED"
PRACTICE_PARENT_CANCELLED_REASON = "Bracket exit cancelled: its entry was cancelled"
PRACTICE_PARENT_EXPIRED_REASON = "Bracket exit cancelled: its entry expired at the session close"
# A bracket whose prices do not surround the entry, refused with the execution
# door's own code (execution/validate.py) so one word reaches the blotter.
PRACTICE_BRACKET_GEOMETRY_CODE = "BRACKET_GEOMETRY"
PRACTICE_BRACKET_QTY_CODE = "QTY_INVALID"

# ---------------------------------------------------------------------------
# Market orders need regular hours (operator decision, 2026-09-21)
# ---------------------------------------------------------------------------
# No US exchange accepts an unpriced order outside 09:30-16:00 ET and IBKR
# holds an RTH-only MKT until the next open (Warning 399), so a market order
# sent after hours is a blind market-on-open, never a fill now. The execution
# door refuses it on every venue (execution/session_gate.py) and the practice
# broker repeats the check (practice/order_rules.py); protective sources are
# exempt. Named here, like TIF_INVALID, so one word reaches the blotter.
MKT_OUTSIDE_RTH_CODE = "MKT_OUTSIDE_RTH"
MKT_OUTSIDE_RTH_REASON = (
    "Market orders are not accepted outside regular hours (09:30-16:00 ET) "
    "-- use a limit at the ask"
)
