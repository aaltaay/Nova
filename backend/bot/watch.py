"""Halt/LULD snapshots for allowlist ∩ live focus (brain Eyes)."""
from __future__ import annotations

from typing import Any

from bot.eligibility import eligible_symbols
from bot.packs import catalog
from bot.session import public_view


def halt_watch(row: dict[str, Any]) -> dict[str, Any]:
    from ibkr import halt_status

    symbols = eligible_symbols(row)
    items: list[dict[str, Any]] = []
    for symbol in symbols:
        snap = halt_status.snapshot(symbol)
        last = None
        position_qty = 0.0
        try:
            from bot.quotes import last_quote

            quote = last_quote(symbol) or {}
            last = quote.get("price")
        except Exception:
            last = None
        try:
            from ibkr import account as _account

            position_qty = float(_account.long_qty(symbol) or 0)
        except Exception:
            position_qty = 0.0
        items.append(
            {
                "symbol": symbol,
                "halted": bool(snap and snap.get("halted")),
                "halt": snap,
                "last": last,
                "position_qty": position_qty,
            }
        )
    view = public_view(row)
    return {
        "symbols": items,
        "active_pack": view.get("active_pack"),
        "packs": catalog(),
        "live_fire_ready": bool(view.get("live_fire_ready")),
        "eligible": symbols,
    }
