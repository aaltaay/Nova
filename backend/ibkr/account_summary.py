"""Parse IBKR accountValues / accountSummary items into the snapshot dict."""
from __future__ import annotations

_SUMMARY_NUMERIC_TAGS = frozenset({
    "NetLiquidation",
    "TotalCashValue",
    "BuyingPower",
    "UnrealizedPnL",
    "RealizedPnL",
    "GrossPositionValue",
})
_SUMMARY_STRING_TAGS = frozenset({"AccountType"})
SUMMARY_TAGS = _SUMMARY_NUMERIC_TAGS | _SUMMARY_STRING_TAGS
_ALLOWED_CURRENCIES = frozenset({"USD", "BASE", ""})


def summary_from_items(items: list, *, mode: str) -> dict:
    """Keep numeric tags as floats. AccountType stays a raw IBKR string."""
    summary: dict = {"connected": True, "mode": mode}
    for item in items:
        tag = getattr(item, "tag", None)
        if tag not in SUMMARY_TAGS:
            continue
        currency = getattr(item, "currency", "") or ""
        if currency and currency not in _ALLOWED_CURRENCIES:
            continue
        raw = getattr(item, "value", None)
        if tag in _SUMMARY_STRING_TAGS:
            if raw in (None, ""):
                summary[tag] = None
            else:
                text = str(raw).strip()
                summary[tag] = text or None
            continue
        try:
            summary[tag] = float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            summary[tag] = None
    return summary
