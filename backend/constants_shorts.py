"""Short selling tunables and reason codes (ADR 048).

Owner: backend/short_sale/. Not re-exported from the constants barrel: only the short check
and its readers import them.

The margin numbers are the published rules the operator's plan states (ADR 048 decision 2),
used when IBKR's what-if cannot answer; the cushion, the equity floor and the hours are the
operator's rules. Numbers marked CHOSEN were left open by the plan.
"""
from __future__ import annotations

# -- The published maintenance a short needs, per share (FINRA 4210(c) and IBKR's short rules).
SHORT_MAINT_LOW_PRICE = 2.50          # under this price: SHORT_MAINT_LOW_PER_SHARE a share
SHORT_MAINT_LOW_PER_SHARE = 2.50
SHORT_MAINT_MID_PRICE = 5.00          # SHORT_MAINT_LOW_PRICE up to this: 100% of value
SHORT_MAINT_MID_PER_SHARE = 5.00      # SHORT_MAINT_MID_PRICE up to SHORT_MAINT_HIGH_PRICE: this a share
SHORT_MAINT_HIGH_PRICE = 16.67        # above this: SHORT_MAINT_HIGH_PCT of value
SHORT_MAINT_HIGH_PCT = 0.30
LONG_MAINT_PCT = 0.25                 # a long's published maintenance: 25% of value

# -- The account a short needs.
SHORT_MIN_EQUITY = 2_000.0            # FINRA 4210(b)(2): no credit, so no short, under this equity
SHORT_CUSHION_PCT = 0.25              # IBKR must not liquidate within a 25% move against the short
SHORT_MARGIN_SOURCE_PUBLISHED = "published rules"   # the label a figure from these rules carries

# -- The liquidation price solver (short_sale.margin): bisection steps and the price it stops at.
SHORT_LIQ_BISECT_STEPS = 60
SHORT_LIQ_TOLERANCE = 1e-6

# -- Reason codes the short check refuses with (ADR 009's SHORT_DISABLED, SHORT_NOT_SHORTABLE and
# SHORT_STALE_BORROW stay in ibkr.shortability / execution.validate).
SHORT_WHILE_LONG = "SHORT_WHILE_LONG"             # the account holds the stock long: Nova never flips
SHORT_NOT_MARGIN = "SHORT_NOT_MARGIN"             # the account is not a margin account
SHORT_EQUITY = "SHORT_EQUITY"                     # equity under SHORT_MIN_EQUITY
SHORT_MARGIN = "SHORT_MARGIN"                     # the requirement does not fit the account
SHORT_MARGIN_UNKNOWN = "SHORT_MARGIN_UNKNOWN"     # the account's equity or margin cannot be read
SHORT_CUSHION = "SHORT_CUSHION"                   # IBKR would liquidate within SHORT_CUSHION_PCT
SHORT_BORROW_TOO_SMALL = "SHORT_BORROW_TOO_SMALL"  # borrow does not cover the order + short + in flight
SHORT_NEEDS_LIMIT = "SHORT_NEEDS_LIMIT"           # a short entry is a limit order (ADR 048 1.6)
