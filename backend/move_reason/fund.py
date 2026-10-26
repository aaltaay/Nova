"""A fund says so, in its own name (ADR 028 amendment 4, 2026-10-26). Pure: no I/O, no clock.

A symbol Yahoo calls a fund (``quote_type`` ``ETF``, which Yahoo also gives ETNs) moves with what it tracks, not on
company news: BRZD +76% and BZQ +50% on 2026-10-26 were inverse Brazil funds the day after Lula won Brazil's
runoff, and the read called them unexplained. The read now says it is a fund and quotes the fund's own name
("ProShares UltraShort MSCI Brazil Capped"); it reads nothing out of that name. Reading the side, the multiple and
what a fund tracks from its name was tried and failed its held-back bar four times (ADR 028 amendment 4, "The
held-back record"): every fix moved the misses elsewhere, while the name itself is never wrong.

Owner: this module (no state).
"""
from __future__ import annotations

from typing import Any

from constants_move_reason import MOVE_FUND_QUOTE_TYPES

CAUSE_LABEL = "A fund: it moves with what it tracks, not on company news"


def is_fund(quote_type: str | None) -> bool | None:
    """True / False from Yahoo's ``quote_type``; None while it is unknown."""
    if not quote_type:
        return None
    return quote_type.upper() in MOVE_FUND_QUOTE_TYPES


def fact(name: str | None) -> dict[str, Any]:
    """``{name}``: the fund's name as Yahoo gives it, untouched (None when Yahoo gives none)."""
    return {"name": (name or "").strip() or None}


def named(fund: dict[str, Any], quote_type: str | None) -> str:
    """"ProShares UltraShort MSCI Brazil Capped", or "A fund (Yahoo: etf)" when Yahoo gives no name."""
    return fund.get("name") or f"A fund (Yahoo: {(quote_type or 'fund').lower()})"
