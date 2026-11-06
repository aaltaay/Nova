"""The AI groups on the Market wire: each group's stocks priced by IBKR, and their plain average.

Nova's own grouping (``MARKET_THEMES``), not an index. A stock IBKR has not priced reads ``null`` and stays out of the
average; a group with no prices has no average.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from constants_market_board import MARKET_THEME_FRESH_SEC, MARKET_THEMES
from market_board.state import Store

RULE = "Each group's change is the plain average of its priced stocks today, not weighted by size."
PREFIX = "theme_quotes:"


def fresh_quotes(st: Store, now: float) -> dict[str, Any]:
    """Every group's quotes younger than ``MARKET_THEME_FRESH_SEC``, by each answer's own time: ``Store.get`` keeps
    a failed read's answer for ``MARKET_STALE_MAX_SEC``, longer than a price may count here."""
    out: dict[str, Any] = {}
    for value, at in st.entries(lambda key: key.startswith(PREFIX)).values():
        if now - at <= MARKET_THEME_FRESH_SEC and isinstance(value, dict):
            out.update(value)
    return out


def _change(quote: Mapping | None) -> float | None:
    price, prev = (quote or {}).get("price"), (quote or {}).get("prev_close")
    return round(100.0 * (price / prev - 1.0), 2) if price is not None and prev else None


def group(spec: Mapping, quotes: Mapping) -> dict[str, Any]:
    rows = [{"symbol": s, "last": (quotes.get(s) or {}).get("price"), "change_pct": _change(quotes.get(s))}
            for s in spec["symbols"]]
    known = [r["change_pct"] for r in rows if r["change_pct"] is not None]
    return {"id": spec["id"], "label": spec["label"], "priced": len(known), "total": len(rows),
            "change_pct": round(sum(known) / len(known), 2) if known else None, "rows": rows}


def board(quotes: Mapping) -> dict[str, Any]:
    return {"rule": RULE, "groups": [group(spec, quotes) for spec in MARKET_THEMES]}
