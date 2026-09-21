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
# Reg T initial margin is 50 % of the purchase, so overnight buying power is
# 2x equity (12 CFR 220.12; QuantConnect's IB model also grants 2x on
# equities). Applied as equity * mult.
PRACTICE_MARGIN_OVERNIGHT_MULT = 2.0
# FINRA Rule 4210(f)(8)(B)(ii): day-trading buying power is four times the
# prior close's maintenance-margin excess for a pattern day trader
# (https://www.finra.org/rules-guidance/key-topics/margin-accounts).
PRACTICE_MARGIN_INTRADAY_MULT = 4.0
# FINRA 4210(f)(8)(B)(iv): a pattern day trader must hold USD 25,000 of
# equity to keep day-trading buying power; below it the practice account
# falls back to the overnight multiplier.
PRACTICE_PDT_MIN_EQUITY = 25_000.0

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
