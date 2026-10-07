"""LULD band tunables (ADR 047). Owner: backend/luld/.

The rule numbers are the LULD Plan's own (Amendment 20, Section V and Appendix A;
the Nasdaq LULD FAQ), so they are not tunables: changing one makes Nova's line
disagree with the exchanges'. The rest say how Nova reads its own data.
"""
from __future__ import annotations

LULD_SCHEMA_VERSION = 1
# NOVA_LULD=0 stops the calculation (no worker, no frames, no rows).
LULD_ENV = "NOVA_LULD"

# -- the Plan's rules ---------------------------------------------------------------------------
# The reference is the arithmetic mean of eligible trades over the preceding five minutes.
LULD_WINDOW_SEC = 300.0
# A new reference replaces the one in force when the mean moves 1% or more from it ...
LULD_MOVE_FRACTION = 0.01
# ... and each new reference stays in force at least 30 seconds (Section V(A)(2)).
LULD_REF_MIN_SEC = 30.0
# A stock whose NBBO rests on a band for 15 seconds is paused by its listing exchange.
LULD_LIMIT_STATE_SEC = 15.0
# The open: the first reference is the listing exchange's opening price when it opens
# within five minutes of 09:30 (Section V(B)); else the five-minute mean then.
LULD_OPEN_GRACE_SEC = 300.0
# Percentage parameters, by the previous close on the listing exchange (Appendix A).
LULD_PRICE_HIGH = 3.00          # more than this: Tier 1 5%, Tier 2 10%
LULD_PRICE_LOW = 0.75           # this up to and including $3.00: 20%
LULD_PCT_TIER1 = 0.05
LULD_PCT_TIER2 = 0.10
LULD_PCT_MID = 0.20
LULD_LOW_DOLLARS = 0.15         # under $0.75: the lesser of $0.15 ...
LULD_LOW_PCT = 0.75             # ... or 75%
# 15:35-16:00 ET: doubled for every Tier 1 stock and Tier 2 stocks at or under $3.00.
LULD_CLOSE_DOUBLE_MIN_ET = 15 * 60 + 35
# A lower band under one cent is no band (the Nasdaq FAQ's closing note for sub-$0.75 names).
LULD_MIN_PRICE = 0.01

# -- how Nova reads its data --------------------------------------------------------------------
# Prices are counted in ten-thousandths of a dollar, so a five-minute sum is exact.
LULD_PRICE_SCALE = 10_000
# A quote within this of a band is resting on it (prices are in cents above $1).
LULD_AT_BAND_EPS = 0.005
# The opening print is accepted from this long before 09:30:00 (Nova's clock runs a
# little ahead of IBKR's: APUS's AMEX opening print arrived at 09:29:59.8, 2026-09-24).
LULD_OPEN_EARLY_SEC = 10.0
# Prints from these venues are trade reports, never a listing exchange's (re)opening.
LULD_REPORT_VENUES: frozenset[str] = frozenset({"FINRA", "ADF", "TRF", "OTC"})
# Sale-condition codes of the (re)opening prints: UTP "O" Opening Prints / CTA "O" Market
# Center Opening Trade, and "5" Re-Opening Prints / Market Center Reopening Trade.
LULD_OPEN_CONDITION = "O"
LULD_REOPEN_CONDITION = "5"
# Without a (re)opening seen, Nova needs this much unbroken tape before it can take the
# five-minute mean -- and its band is then approximate (``exact: false``).
LULD_WARM_SEC = LULD_WINDOW_SEC
# A tracker that heard nothing for this long is forgotten (the line was given back).
LULD_FORGET_SEC = 30 * 60
# A gap in the tape longer than this breaks the calculation's exactness.
LULD_TAPE_GAP_SEC = 20.0
# Reference changes kept for the hover.
LULD_HISTORY_KEEP = 8
# The worker's queue (enqueue only on the IB loop, ADR 010).
LULD_QUEUE_MAX = 200_000
LULD_TICK_SEC = 0.25
# How often a depth socket asks for news, and how often it repeats an unchanged view.
LULD_PUSH_SEC = 0.25
LULD_REPEAT_SEC = 5.0
# Near a band: the strip turns amber within this fraction of the price ...
LULD_NEAR_FRACTION = 0.02
# ... or within this many cents of it, whichever is wider.
LULD_NEAR_CENTS = 0.05

# -- the tier (Appendix A: Tier 1 is the S&P 500, the Russell 1000 and listed ETPs) --------------
# Nova keeps no index membership list. At or under $3.00 the tiers' bands are the same, so the
# tier matters only above it, and there Nova reads the company's size: a company this large is
# in the Russell 1000 ...
LULD_TIER1_MIN_MARKET_CAP = 15e9
# ... and one this small is not (the Russell 1000's smallest member was over $4B at its June
# reconstitution). Between them Nova takes the likelier side of about the cut-off, and says so.
LULD_TIER2_MAX_MARKET_CAP = 2e9
LULD_TIER_GUESS_MARKET_CAP = 4.5e9

# -- words ----------------------------------------------------------------------------------------
LULD_NOTE = (
    "Nova's calculation from the published Limit Up-Limit Down rules -- not the band the "
    "exchanges' data feed (the SIP) publishes, which IBKR does not pass on."
)
LULD_RULES_TEXT = (
    "The reference is the average trade price of the last 5 minutes (the open or reopen price "
    "first), replaced only when that average moves 1% or more and the old one has stood 30 s. "
    "Band = reference +/- the percentage set by the previous close. A stock whose best offer "
    "sits on the lower band (or best bid on the upper) for 15 s is paused for 5 minutes."
)
