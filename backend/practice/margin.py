"""Buying power for the practice account (FINRA 4210 intraday margin; practice-account.md, section 2).

FINRA's intraday margin rule (effective 2026-06-04) replaced the pattern day
trader line: equity must cover the maintenance margin of the positions held
at any moment. Nova uses ``PRACTICE_MARGIN_INTRADAY_MULT`` (4x, the 25 %
maintenance margin on long stock) whenever net liquidation is at or above
``PRACTICE_MARGIN_MIN_EQUITY`` (USD 2,000, the minimum to borrow at all);
below it the account buys with its own cash (``PRACTICE_CASH_MULT``, 1x).
The same multiplier applies at any hour -- there is no end-of-day Reg T call
and no forced liquidation (a named gap, section 4).

Buying power is cash-based: ``equity * multiplier - gross position value``.
A trade that reduces a held position (a sell against a long, a buy against a
short) never needs buying power; only the shares that open or add to exposure
are charged against it.
"""
from __future__ import annotations

from constants_practice import (
    PRACTICE_CASH_MULT,
    PRACTICE_MARGIN_INTRADAY_MULT,
    PRACTICE_MARGIN_MIN_EQUITY,
)

_EPS = 1e-9


def multiplier(net_liquidation: float) -> float:
    """4x intraday margin at or above the USD 2,000 margin minimum, cash (1x) below it."""
    if float(net_liquidation) >= PRACTICE_MARGIN_MIN_EQUITY:
        return PRACTICE_MARGIN_INTRADAY_MULT
    return PRACTICE_CASH_MULT


def buying_power(net_liquidation: float, gross_position_value: float) -> float:
    """``max(0, equity * multiplier - gross position value)``."""
    equity = float(net_liquidation)
    return max(0.0, equity * multiplier(equity) - abs(float(gross_position_value)))


def opening_qty(side: str, qty: float, held: float) -> float:
    """Shares of ``qty`` that increase exposure; the rest reduce ``held`` first."""
    shares = abs(float(qty))
    cur = float(held)
    if (side or "").upper() == "BUY":
        return shares if cur >= -_EPS else max(0.0, shares - (-cur))
    return shares if cur <= _EPS else max(0.0, shares - cur)


def order_cost(side: str, qty: float, price: float, held: float) -> float:
    """Buying power an order consumes: only its opening shares, at ``price``."""
    return opening_qty(side, qty, held) * abs(float(price))


def check(
    side: str,
    qty: float,
    price: float,
    held: float,
    net_liquidation: float,
    gross_position_value: float,
) -> tuple[bool, float, float]:
    """``(ok, needed, available)``; a reducing trade needs nothing and is always ok."""
    needed = order_cost(side, qty, price, held)
    available = buying_power(net_liquidation, gross_position_value)
    return needed <= available + _EPS, needed, available
