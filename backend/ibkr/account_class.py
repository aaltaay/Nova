"""Cash vs Margin class for the header chip and ticket Short visibility.

TWS AccountType is ownership (INDIVIDUAL / LLC / IRA), not Cash vs Margin.
A live connected snapshot is always cash or margin. Unknown is not a class.

IBKR's own word comes first: ``TradingType-S`` ("Account Type" in IBKR's Account Value Keys). The
operator's Live cash account reads ``STKCASH`` (2026-11-17); ``STKMRGN`` is read as margin by its
name, not yet seen on a Nova account. ``STKNOPT`` says neither (it was seen beside cash figures), so
it falls to the figures. The figures only ever prove margin: buying power at
``IBKR_ACCOUNT_CLASS_MARGIN_MIN_BP_RATIO`` or more of excess liquidity or of cash is leverage a cash
account never has. Cash is what is left, never a band of its own: a margin account holding a short
carries the short's proceeds as cash, so "buying power under cash" is not proof of a cash account.

``account_class`` takes the operator's ``.env`` override (``IBKR_ACCOUNT_CLASS``) first;
``ibkr_account_class`` is IBKR's own figures alone, and ``account_class_source`` says which
decided. A Live short needs IBKR's word, never the override (ADR 048 step 6).
"""
from __future__ import annotations

import os

from constants_ibkr import (
    IBKR_ACCOUNT_CLASS_ENV,
    IBKR_ACCOUNT_CLASS_MARGIN_MIN_BP_RATIO,
)

AccountClass = str  # "cash" | "margin"

_CASH_TOKENS = frozenset({"CASH", "CASH ACCOUNT", "STKCASH"})
_MARGIN_TOKENS = frozenset({
    "MARGIN",
    "MRGN",
    "STKMRGN",
    "REGT",
    "REGT MARGIN",
    "REG T MARGIN",
    "PORTFOLIO MARGIN",
    "PMRGN",
    "UNCLEARED MARGIN ACCOUNT",
    "PM",
})


def _as_float(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _token_class(raw: object) -> AccountClass | None:
    key = str(raw or "").strip().upper()
    if key in _CASH_TOKENS:
        return "cash"
    if key in _MARGIN_TOKENS:
        return "margin"
    return None


def account_class_override() -> AccountClass | None:
    raw = (os.environ.get(IBKR_ACCOUNT_CLASS_ENV) or "").strip().lower()
    if raw in ("cash", "margin"):
        return raw
    return None


def classify_account_class(summary: dict) -> AccountClass:
    """Return cash or margin. Never unknown. Never invent Margin from a weak band."""
    override = account_class_override()
    if override:
        return override
    return ibkr_account_class(summary)


def ibkr_account_class(summary: dict) -> AccountClass:
    """Cash or margin from IBKR's own figures alone -- the override never counts."""
    for key in ("AccountType", "TradingType"):
        kind = _token_class(summary.get(key))
        if kind:
            return kind
    bp = _as_float(summary.get("BuyingPower"))
    if bp is None:
        return "cash"
    margin_min = float(IBKR_ACCOUNT_CLASS_MARGIN_MIN_BP_RATIO)
    for key in ("ExcessLiquidity", "TotalCashValue"):
        base = _as_float(summary.get(key))
        if base is not None and base > 0 and bp >= base * margin_min:
            return "margin"
    return "cash"


def attach_account_class(summary: dict) -> dict:
    """Stamp account_class on a connected snapshot. Leave disconnected alone."""
    if not summary.get("connected"):
        return summary
    out = dict(summary)
    out["account_class"] = classify_account_class(out)
    out["ibkr_account_class"] = ibkr_account_class(out)
    out["account_class_source"] = "override" if account_class_override() else "ibkr"
    return out
