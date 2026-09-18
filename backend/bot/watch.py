"""Halt/LULD + shared-quote snapshots for allowlist ∩ live focus (brain Eyes)."""
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
        bid = None
        ask = None
        last_update_ts = None
        position_qty = 0.0
        try:
            from bot.quotes import eyes_row

            quote = eyes_row(symbol)
            last = quote.get("last")
            bid = quote.get("bid")
            ask = quote.get("ask")
            last_update_ts = quote.get("last_update_ts")
        except Exception:
            last = None
            bid = None
            ask = None
            last_update_ts = None
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
                "bid": bid,
                "ask": ask,
                "last_update_ts": last_update_ts,
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
