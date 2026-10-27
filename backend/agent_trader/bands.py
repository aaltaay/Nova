"""The LULD band in what Claude reads (ADR 068 decision 16, with the halts; ADR 047's band, not a new one).

``luld.live.view`` is the band source: Nova computes it from a stock's Time & Sales, so a stock without a tape line
answers its own ``state`` (``unknown``, ``off``, ...) with no band, and nothing here fills one in. Read-only.

- ``of``: ``{upper, lower, pct_to_upper, pct_to_lower, state, exact}`` for ``/look`` and the eye;
- ``at_limit``: the book's best bid sits at the upper band with nothing offered at or under it -- buyers pinned by
  the band, not support (the AIOK halt, 2026-10-27);
- ``buy_warning``: a buy priced within ``AGENT_LULD_WARN_PCT`` of the upper band, or over it -- a warning, never a
  refusal (Paper, to learn).
"""
from __future__ import annotations

import logging
from typing import Any

from agent_trader.constants_agent_trader import AGENT_LULD_WARN_PCT

logger = logging.getLogger(__name__)


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out > 0 else None


def view(symbol: str) -> dict[str, Any] | None:
    from luld import live

    try:
        return live.view(symbol)
    except Exception:
        logger.warning("AGENT bands: %s's LULD view could not be read", symbol, exc_info=True)
        return None


def of(symbol: str, last: float | None, band: dict[str, Any] | None = None) -> dict[str, Any]:
    """The band as Claude reads it; null numbers where the source has no band."""
    v = band if band is not None else view(symbol)
    if v is None:
        return {"upper": None, "lower": None, "pct_to_upper": None, "pct_to_lower": None, "state": "unknown",
                "exact": False}
    upper, lower, px = _num(v.get("upper")), _num(v.get("lower")), _num(last)
    return {"upper": upper, "lower": lower,
            "pct_to_upper": (upper / px - 1.0) * 100.0 if upper and px else None,
            "pct_to_lower": (1.0 - lower / px) * 100.0 if lower and px else None,
            "state": v.get("state"), "exact": bool(v.get("exact"))}


def at_limit(book: dict[str, Any] | None, band: dict[str, Any]) -> bool:
    """The best bid is at or over the upper band and nothing is offered at or under it."""
    upper = _num(band.get("upper"))
    if upper is None or not book:
        return False
    bids = [p for p in (_num(r.get("price")) for r in book.get("bids") or []) if p]
    asks = [p for p in (_num(r.get("price")) for r in book.get("asks") or []) if p]
    return bool(bids) and max(bids) >= upper - 1e-9 and not any(a <= upper + 1e-9 for a in asks)


def buy_warning(symbol: str, price: float, band: dict[str, Any] | None = None) -> str | None:
    """Words when a buy at ``price`` sits within ``AGENT_LULD_WARN_PCT`` of the upper band or over it, else None."""
    b = of(symbol, price, band)
    upper = b["upper"]
    if upper is None:
        return None
    if price >= upper - 1e-9:
        return (f"the buy at {price:g} is at or over {symbol}'s upper LULD band {upper:g}: a fill there can be the "
                "last print before a limit-up pause")
    if price >= upper * (1.0 - AGENT_LULD_WARN_PCT / 100.0):
        return (f"the buy at {price:g} is {(upper / price - 1.0) * 100.0:.2f}% under {symbol}'s upper LULD band "
                f"{upper:g}: a limit-up pause may come before the target")
    return None
