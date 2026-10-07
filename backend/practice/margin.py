"""Margin for the practice account (FINRA 4210 intraday margin; ADR 048; practice-account.md, section 2).

FINRA's intraday margin rule (effective 2026-06-04) replaced the pattern day trader line: equity
must cover the maintenance margin of the positions held at any moment. At or above
``PRACTICE_MARGIN_MIN_EQUITY`` (USD 2,000, the minimum to borrow at all) the account is a margin
account:

- a position's maintenance is its stock's published requirement (``short_sale.margin``: 25% of a
  long's value; a short's tiers) times that stock's ratio -- IBKR's what-if over the published rule
  when IBKR answered for it (``short_sale.whatif``), else 1 (ADR 048 decision 2: longs use margin too);
- excess liquidity is equity less every position's maintenance;
- an opening long fits when its requirement fits the excess, so buying power is the excess over the
  25% a long needs (``PRACTICE_MARGIN_INTRADAY_MULT``, 4x): with longs only, ``equity * 4 - gross``;
- an opening short fits when its requirement fits the excess (the door's short check adds the 25%
  cushion, ADR 048 1.5).

Below the minimum the account is a cash account (``PRACTICE_CASH_MULT``, 1x): longs buy with cash
on hand and nothing can be shorted. The same rule applies at any hour -- there is no end-of-day
Reg T call. A trade that reduces a held position (a sell against a long, a buy against a short)
never needs margin; only the shares that open or add to exposure are charged.
"""
from __future__ import annotations

from typing import Any, Callable

from constants_practice import (
    PRACTICE_CASH_MULT,
    PRACTICE_MARGIN_INTRADAY_MULT,
    PRACTICE_MARGIN_MIN_EQUITY,
)
from short_sale import margin as published

_EPS = 1e-9

# ``(symbol, "long" | "short") -> (ratio, source label)``: the stock's IBKR ratio, or 1 (published).
RatioFn = Callable[[str, str], tuple[float, str]]


def published_ratio(symbol: str, position_side: str) -> tuple[float, str]:
    """The published rules: ratio 1, for a ledger no venue has given IBKR's figures."""
    del symbol, position_side
    from constants_shorts import SHORT_MARGIN_SOURCE_PUBLISHED

    return 1.0, SHORT_MARGIN_SOURCE_PUBLISHED


def multiplier(net_liquidation: float) -> float:
    """4x intraday margin at or above the USD 2,000 margin minimum, cash (1x) below it."""
    if float(net_liquidation) >= PRACTICE_MARGIN_MIN_EQUITY:
        return PRACTICE_MARGIN_INTRADAY_MULT
    return PRACTICE_CASH_MULT


def is_margin(net_liquidation: float) -> bool:
    return float(net_liquidation) >= PRACTICE_MARGIN_MIN_EQUITY


def position_maintenance(row: dict[str, Any], ratio: RatioFn = published_ratio) -> float:
    """One ``position_rows`` row's maintenance at its mark."""
    qty = float(row.get("qty") or 0)
    if abs(qty) < _EPS:
        return 0.0
    side = "short" if qty < 0 else "long"
    mark = float(row.get("market_price") or row.get("avg_cost") or 0)
    factor, _ = ratio(str(row.get("symbol") or ""), side)
    return published.requirement(side, mark, abs(qty), factor)


def maintenance(rows: list[dict[str, Any]], ratio: RatioFn = published_ratio) -> float:
    """Every held position's maintenance."""
    return sum(position_maintenance(row, ratio) for row in rows)


def buying_power(net_liquidation: float, gross_position_value: float, maint: float | None = None) -> float:
    """What an opening long may still buy: the excess over the 25% a long needs, or cash below USD 2,000.

    ``maint`` defaults to a long-only account's 25% of gross, which is ``equity * 4 - gross``.
    """
    equity = float(net_liquidation)
    gross = abs(float(gross_position_value))
    if not is_margin(equity):
        return max(0.0, equity * PRACTICE_CASH_MULT - gross)
    held = gross / PRACTICE_MARGIN_INTRADAY_MULT if maint is None else float(maint)
    return max(0.0, (equity - held) * PRACTICE_MARGIN_INTRADAY_MULT)


def opening_qty(side: str, qty: float, held: float) -> float:
    """Shares of ``qty`` that increase exposure; the rest reduce ``held`` first."""
    shares = abs(float(qty))
    cur = float(held)
    if (side or "").upper() == "BUY":
        return shares if cur >= -_EPS else max(0.0, shares - (-cur))
    return shares if cur <= _EPS else max(0.0, shares - cur)


def order_cost(side: str, qty: float, price: float, held: float) -> float:
    """Buying power an order consumes at the published rules: only its opening shares, at ``price``."""
    return opening_qty(side, qty, held) * abs(float(price))


def check(
    side: str,
    qty: float,
    price: float,
    held: float,
    net_liquidation: float,
    gross_position_value: float,
    *,
    maint: float | None = None,
    ratio: float = 1.0,
) -> tuple[bool, float, float]:
    """``(ok, needed, available)``; a reducing trade needs nothing and is always ok.

    A long is measured in buying power (its opening value times the stock's ``ratio`` against the
    buying power); a short in margin (its requirement against the excess, none below USD 2,000).
    """
    opening = opening_qty(side, qty, held)
    if opening <= _EPS:
        return True, 0.0, buying_power(net_liquidation, gross_position_value, maint)
    equity = float(net_liquidation)
    if (side or "").upper() == "BUY":
        factor = float(ratio) if is_margin(equity) else 1.0
        needed = opening * abs(float(price)) * factor
        available = buying_power(equity, gross_position_value, maint)
        return needed <= available + _EPS, needed, available
    needed = published.requirement("short", price, opening, ratio)
    held_maint = abs(float(gross_position_value)) / PRACTICE_MARGIN_INTRADAY_MULT if maint is None else float(maint)
    available = max(0.0, equity - held_maint) if is_margin(equity) else 0.0
    return needed <= available + _EPS, needed, available
