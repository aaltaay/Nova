"""Which trade prints may set a price -- a candle's open / high / low / close, or the last.

The consolidated tape reports every trade, but an odd lot, an average-price or
derivatively priced trade, a prior-reference print and a few others are
reported for volume only and never move the price (codes in
``constants_tape.py``). Time & Sales shows them all; a candle must not. PLTR ``4 W``
prints $2-3 under the market drew 10-second wicks no other chart showed
(2026-09-23).

IBKR says it two ways: ``tickAttribLast.unreported`` on the print, and the
codes in ``specialConditions``. A print sets a price only when neither
excludes it. Over IBKR's own 10-second TRADES bars (AAPL, GRML, IMCC, DAIC,
MEDS) this rule took the worst high / low miss from $8.50 to $0.18, and bar
volume matched (median ratio 1.00), so volume follows the same prints.

Pure: stdlib and constants only (domain layer).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from constants_tape import TAPE_NO_PRICE_CONDITIONS


def sets_price(conditions: str | None, *, unreported: bool | None = None) -> bool:
    """True when a print may move a candle or the last."""
    if unreported:
        return False
    return TAPE_NO_PRICE_CONDITIONS.isdisjoint(str(conditions or ""))


def row_sets_price(row: Mapping[str, Any]) -> bool:
    """A print row's verdict: its own ``sets_price`` when stamped, else its conditions."""
    stamped = row.get("sets_price")
    if isinstance(stamped, bool):
        return stamped
    return sets_price(row.get("conditions"), unreported=bool(row.get("unreported")))


def tape_flags(row: Mapping[str, Any]) -> dict[str, bool]:
    """The two fields a Time & Sales print carries: IBKR's ``unreported`` flag and the verdict.

    A row recorded before the fields existed is judged by its conditions, so a
    replayed odd lot reads the same as a live one (#543).
    """
    return {"unreported": bool(row.get("unreported")), "sets_price": row_sets_price(row)}
