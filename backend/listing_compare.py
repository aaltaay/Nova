"""Build side-by-side Alpaca vs IBKR listing payloads for the quote panel."""
from __future__ import annotations

from typing import Any


def alpaca_listing_from_asset(asset: dict | None) -> dict[str, Any]:
    """Normalize Alpaca /v2/assets fields with explicit short-type wording."""
    a = asset or {}
    shortable = a.get("shortable")
    etb = a.get("easy_to_borrow")
    short_type: str | None = None
    short_detail: str | None = None
    if shortable is True and etb is True:
        short_type = "easy_to_borrow"
        short_detail = (
            "Alpaca: shortable + easy_to_borrow (ETB). "
            "This is Alpaca inventory — not IBKR locate."
        )
    elif shortable is True and etb is False:
        short_type = "hard_to_borrow"
        short_detail = (
            "Alpaca: shortable but not easy_to_borrow (HTB at Alpaca). "
            "Do not treat as IBKR short inventory."
        )
    elif shortable is False:
        short_type = "not_shortable"
        short_detail = "Alpaca: not shortable on their platform."
    elif shortable is None:
        short_type = None
        short_detail = "Alpaca shortable flag unavailable."

    return {
        "source": "alpaca_assets",
        "status": a.get("status"),
        "tradable": a.get("tradable"),
        "shortable": shortable,
        "easy_to_borrow": etb,
        "short_type": short_type,
        "short_type_detail": short_detail,
        "marginable": a.get("marginable"),
        "fractionable": a.get("fractionable"),
        "maintenance_margin_requirement": a.get("maintenance_margin_requirement"),
        "margin_requirement_long": a.get("margin_requirement_long"),
        "margin_requirement_short": a.get("margin_requirement_short"),
        "asset_class": a.get("asset_class"),
        "exchange": a.get("exchange"),
        "attributes": a.get("attributes") or [],
        "error": None if a else "Alpaca asset metadata empty (keys or symbol miss)",
    }


def build_listing_compare(symbol: str, asset: dict | None) -> dict[str, Any]:
    """Alpaca from asset cache + IBKR short/qualify snapshot (best-effort)."""
    from ibkr.listing_flags import fetch_listing_flags_sync

    return {
        "symbol": (symbol or "").strip().upper(),
        "alpaca": alpaca_listing_from_asset(asset),
        "ibkr": fetch_listing_flags_sync(symbol),
    }
