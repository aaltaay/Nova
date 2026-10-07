"""Margin by the published rules, the liquidation price and the 25% cushion (ADR 048). Pure.

IBKR's what-if is the first source of a requirement (ADR 048 decision 2); these are the published
rules Nova falls back on when IBKR cannot answer, and the label such a figure carries:

- a short's maintenance, per share: $2.50 under $2.50; 100% of the price from $2.50 to $5; $5 from
  $5 to $16.67; 30% of the price above $16.67 (``constants_shorts``);
- a long's: 25% of value.

**The liquidation price** of one position is where the account's equity -- that position marked
at the price, every other position held still -- falls to the maintenance requirement, which is
when IBKR liquidates. For a short of ``qty`` shares marked at ``mark``, with ``equity`` now and
``other_maint`` needed by everything else:

    equity - qty * (p - mark)  <  other_maint + qty * short_maint_per_share(p)

The left side falls and the right side never falls as ``p`` rises (the tiers meet at their edges),
so the first such ``p`` is found by bisection. **The cushion** (ADR 048 1.5): a short is refused
when that price is under ``entry * (1 + SHORT_CUSHION_PCT)``, the price a 25% move against it
reaches.

**IBKR's own figure.** When IBKR's what-if answered for a stock (``short_sale.whatif``), its
maintenance over the published one is that stock's ``ratio`` -- IBKR's extra charge on a volatile
name -- and every function here scales the stock's published maintenance by it. ``ratio`` 1 is the
published rules.
"""
from __future__ import annotations

import math

from constants_shorts import (
    LONG_MAINT_PCT,
    SHORT_CUSHION_PCT,
    SHORT_LIQ_BISECT_STEPS,
    SHORT_LIQ_TOLERANCE,
    SHORT_MAINT_HIGH_PCT,
    SHORT_MAINT_HIGH_PRICE,
    SHORT_MAINT_LOW_PER_SHARE,
    SHORT_MAINT_LOW_PRICE,
    SHORT_MAINT_MID_PER_SHARE,
    SHORT_MAINT_MID_PRICE,
)


def short_maint_per_share(price: float) -> float:
    """The published maintenance one short share needs at ``price``."""
    p = float(price)
    if p < SHORT_MAINT_LOW_PRICE:
        return SHORT_MAINT_LOW_PER_SHARE
    if p < SHORT_MAINT_MID_PRICE:
        return p
    if p <= SHORT_MAINT_HIGH_PRICE:
        return SHORT_MAINT_MID_PER_SHARE
    return SHORT_MAINT_HIGH_PCT * p


def short_requirement(price: float, qty: float) -> float:
    """The published maintenance ``qty`` short shares need at ``price``."""
    return abs(float(qty)) * short_maint_per_share(price)


def long_requirement(price: float, qty: float) -> float:
    """The published maintenance ``qty`` long shares need at ``price``: 25% of value."""
    return abs(float(qty)) * abs(float(price)) * LONG_MAINT_PCT


def requirement(position_side: str, price: float, qty: float, ratio: float = 1.0) -> float:
    """The maintenance ``qty`` shares of a ``"long"`` or ``"short"`` position need at ``price``."""
    if position_side == "short":
        return short_requirement(price, qty) * float(ratio)
    return long_requirement(price, qty) * float(ratio)


def _short_surplus(p: float, *, equity: float, other_maint: float, qty: float, mark: float,
                   ratio: float = 1.0) -> float:
    """Equity over maintenance with the short marked at ``p``; under zero, IBKR liquidates."""
    return equity - qty * (p - mark) - other_maint - qty * short_maint_per_share(p) * ratio


def short_liquidation_price(*, equity: float, other_maint: float, qty: float, mark: float,
                            ratio: float = 1.0) -> float | None:
    """The price at or over ``mark`` at which IBKR would liquidate a short of ``qty`` marked at ``mark``.

    ``mark`` itself when the account is already under its maintenance there; None for no short.
    """
    q = abs(float(qty))
    m = float(mark)
    r = float(ratio)
    if q <= 0 or not math.isfinite(m) or m <= 0 or not (math.isfinite(r) and r > 0):
        return None
    args = {"equity": float(equity), "other_maint": float(other_maint), "qty": q, "mark": m, "ratio": r}
    if _short_surplus(m, **args) < 0:
        return m
    # Every tier needs at least 30% of the price a share, so past this price the surplus is negative.
    hi = max(m, (float(equity) - float(other_maint) + q * m) / (q * (1.0 + SHORT_MAINT_HIGH_PCT * r))) * 1.01 + 0.01
    lo = m
    for _ in range(SHORT_LIQ_BISECT_STEPS):
        mid = (lo + hi) / 2.0
        if _short_surplus(mid, **args) < 0:
            hi = mid
        else:
            lo = mid
        if hi - lo <= SHORT_LIQ_TOLERANCE * max(1.0, m):
            break
    return hi


def long_liquidation_price(*, equity: float, other_maint: float, qty: float, mark: float,
                           ratio: float = 1.0) -> float | None:
    """The price at or under ``mark`` at which IBKR would liquidate a long of ``qty``; None when never.

    ``equity + qty * (p - mark) < other_maint + 0.25 * ratio * qty * p`` solves directly; a price
    under zero means the long alone can never be liquidated (it is paid for).
    """
    q = abs(float(qty))
    m = float(mark)
    r = float(ratio)
    if q <= 0 or not math.isfinite(m) or m <= 0 or not (math.isfinite(r) and r > 0):
        return None
    denominator = q * (1.0 - LONG_MAINT_PCT * r)
    if denominator <= 0:
        return None  # IBKR wants the whole value or more: a price fall alone never liquidates it
    price = (float(other_maint) - float(equity) + q * m) / denominator
    if price <= 0:
        return None
    return min(price, m)


def cushion(*, equity: float, other_maint: float, qty: float, entry: float,
            cushion_pct: float = SHORT_CUSHION_PCT, ratio: float = 1.0) -> dict[str, float | bool | None]:
    """``{ok, fits, liquidation_price, cushion_price, requirement, surplus_at_entry}`` for a short of ``qty`` at ``entry``.

    ``qty`` is the whole short in the stock once this order fills (held + in flight + this order);
    ``other_maint`` everything else's maintenance. ``fits`` -- the requirement fits at the entry;
    ``ok`` -- IBKR would not liquidate within ``cushion_pct`` (which implies ``fits``); ``ratio`` --
    IBKR's charge on this stock over the published one.
    """
    q = abs(float(qty))
    e = float(entry)
    target = e * (1.0 + float(cushion_pct))
    args = {"equity": float(equity), "other_maint": float(other_maint), "qty": q, "mark": e, "ratio": float(ratio)}
    at_entry = _short_surplus(e, **args)
    liq = short_liquidation_price(**args)
    return {
        "ok": _short_surplus(target, **args) >= 0,
        "fits": at_entry >= 0,
        "liquidation_price": liq,
        "cushion_price": target,
        "requirement": short_requirement(e, q) * float(ratio),
        "surplus_at_entry": at_entry,
    }
