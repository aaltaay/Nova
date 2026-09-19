"""Parse IBKR accountValues / accountSummary items into the snapshot dict.

Gap (Gateway / TWS API): official ``AccountSummaryTags.GetAllTags`` has
AccountType, balances, BuyingPower, Init/MaintMarginReq, RegTEquity/RegTMargin,
Leverage -- no CASH / MARGIN / RegT / PortfolioMargin class tag. Live smoke
returned ``AccountType=INDIVIDUAL`` (ownership, same family as LLC / IRA).
``managedAccounts`` is only the account id (paper vs live). ``TradingType-S``
is securities trading-config (often STKNOPT). ``WhatIfPMEnabled`` is a TWS
Portfolio-Margin what-if switch. Leverage is GPV/NLV. InitMarginReq and
BuyingPower are amounts -- never classifiers.

Flex Query ``margin=CASH|MRGN|PMRGN`` and Client Portal Account Management
``margin`` / Margin Type exist, but Nova does not call those APIs.

The snapshot keeps raw AccountType / TradingType / WhatIfPMEnabled / Leverage
for tooltip/debug. ``account_class`` is cash|margin on a connected snapshot
(env override, then tokens, then BP vs cash / ExcessLiquidity, else Cash).
"""
from __future__ import annotations

from ibkr.account_class import attach_account_class

_SUMMARY_NUMERIC_TAGS = frozenset({
    "NetLiquidation",
    "TotalCashValue",
    "BuyingPower",
    "UnrealizedPnL",
    "RealizedPnL",
    "GrossPositionValue",
    "ExcessLiquidity",
    "Leverage",
    "Leverage-S",
})
_SUMMARY_STRING_TAGS = frozenset({
    "AccountType",
    "TradingType-S",
    "WhatIfPMEnabled",
})
SUMMARY_TAGS = _SUMMARY_NUMERIC_TAGS | _SUMMARY_STRING_TAGS
_TAG_ALIAS = {
    "TradingType-S": "TradingType",
    "Leverage-S": "Leverage",
}
_OVERLAY_KEYS = frozenset({
    "AccountType",
    "TradingType",
    "WhatIfPMEnabled",
    "Leverage",
})
_ALLOWED_CURRENCIES = frozenset({"USD", "BASE", ""})


def _snapshot_key(tag: str) -> str:
    return _TAG_ALIAS.get(tag, tag)


def summary_from_items(items: list, *, mode: str) -> dict:
    """Keep numeric tags as floats. AccountType / TradingType stay IBKR strings."""
    summary: dict = {"connected": True, "mode": mode}
    for item in items:
        tag = getattr(item, "tag", None)
        if tag not in SUMMARY_TAGS:
            continue
        currency = getattr(item, "currency", "") or ""
        if currency and currency not in _ALLOWED_CURRENCIES:
            continue
        key = _snapshot_key(str(tag))
        raw = getattr(item, "value", None)
        if tag in _SUMMARY_STRING_TAGS:
            if raw in (None, ""):
                if key not in summary:
                    summary[key] = None
            else:
                text = str(raw).strip()
                if text:
                    summary[key] = text
                elif key not in summary:
                    summary[key] = None
            continue
        try:
            parsed = float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None or key not in summary:
            summary[key] = parsed
    return attach_account_class(summary)


def account_values_items(ib: object) -> list:
    """Cached reqAccountUpdates rows. Empty on failure -- never raise here."""
    getter = getattr(ib, "accountValues", None)
    if getter is None:
        return []
    try:
        raw = getter()
    except Exception:
        return []
    if raw is None:
        return []
    try:
        return list(raw)
    except TypeError:
        return []


def overlay_missing_tags(base: dict, extra: dict) -> dict:
    """Fill config tags that reqAccountSummary does not request from accountValues."""
    out = dict(base)
    for key in _OVERLAY_KEYS:
        if out.get(key) not in (None, ""):
            continue
        value = extra.get(key)
        if value not in (None, ""):
            out[key] = value
    return attach_account_class(out)
