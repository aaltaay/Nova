"""Buying power for the practice account (Reg T / FINRA 4210; practice-account.md, section 2).

Which multiplier Nova uses intraday: ``PRACTICE_MARGIN_INTRADAY_MULT`` (4x,
FINRA 4210 day-trading buying power) whenever net liquidation is at or above
``PRACTICE_PDT_MIN_EQUITY``; below that line the account falls back to the
Reg T overnight multiplier (2x). Nova's bots are day traders, so 4x is the
number they hit. The overnight multiplier applies at any hour -- there is no
end-of-day call and no forced liquidation (a named gap, section 3).

Buying power is cash-based: ``equity * multiplier - gross position value``.
A trade that reduces a held position (a sell against a long, a buy against a
short) never needs buying power; only the shares that open or add to exposure
are charged against it.
"""
from __future__ import annotations

from constants_practice import (
    PRACTICE_MARGIN_INTRADAY_MULT,
    PRACTICE_MARGIN_OVERNIGHT_MULT,
    PRACTICE_PDT_MIN_EQUITY,
)

_EPS = 1e-9


def multiplier(net_liquidation: float) -> float:
    """4x day-trading power above the pattern-day-trader line, Reg T 2x below it."""
    if float(net_liquidation) >= PRACTICE_PDT_MIN_EQUITY:
        return PRACTICE_MARGIN_INTRADAY_MULT
    return PRACTICE_MARGIN_OVERNIGHT_MULT


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
