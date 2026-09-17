"""Cash vs Margin class for the header chip and ticket Short visibility.

TWS AccountType is ownership (INDIVIDUAL / LLC / IRA), not Cash vs Margin.
A live connected snapshot is always cash or margin. Unknown is not a class.
"""
from __future__ import annotations

import os

from constants_ibkr import (
    IBKR_ACCOUNT_CLASS_CASH_MAX_BP_RATIO,
    IBKR_ACCOUNT_CLASS_ENV,
    IBKR_ACCOUNT_CLASS_MARGIN_MIN_BP_RATIO,
)

AccountClass = str  # "cash" | "margin"

_CASH_TOKENS = frozenset({"CASH", "CASH ACCOUNT"})
_MARGIN_TOKENS = frozenset({
    "MARGIN",
    "MRGN",
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
    for key in ("AccountType", "TradingType"):
        kind = _token_class(summary.get(key))
        if kind:
            return kind
    bp = _as_float(summary.get("BuyingPower"))
    cash = _as_float(summary.get("TotalCashValue"))
    excess = _as_float(summary.get("ExcessLiquidity"))
    cash_max = float(IBKR_ACCOUNT_CLASS_CASH_MAX_BP_RATIO)
    margin_min = float(IBKR_ACCOUNT_CLASS_MARGIN_MIN_BP_RATIO)
    if bp is not None and cash is not None and cash > 0:
        if bp <= cash * cash_max:
            return "cash"
        if bp >= cash * margin_min:
            return "margin"
    if bp is not None and excess is not None and excess > 0:
        if bp >= excess * margin_min:
            return "margin"
    return "cash"


def attach_account_class(summary: dict) -> dict:
    """Stamp account_class on a connected snapshot. Leave disconnected alone."""
    if not summary.get("connected"):
        return summary
    out = dict(summary)
    out["account_class"] = classify_account_class(out)
    return out
