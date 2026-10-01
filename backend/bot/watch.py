"""Halt / LULD + shared-quote snapshots for allowlist ∩ live focus (a brain's Eyes)."""
from __future__ import annotations

import logging
from typing import Any

from bot.eligibility import eligible_symbols
from bot.session import public_view

logger = logging.getLogger(__name__)


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
        volume = None
        position_qty: float | None = 0.0
        try:
            from bot.quotes import eyes_row

            quote = eyes_row(symbol)
            last = quote.get("last")
            bid = quote.get("bid")
            ask = quote.get("ask")
            last_update_ts = quote.get("last_update_ts")
            volume = quote.get("volume")
        except Exception:
            logger.warning("bot watch: the %s quote could not be read -- left unknown", symbol, exc_info=True)
        try:
            from ibkr import account as _account

            position_qty = float(_account.long_qty(symbol) or 0)
        except Exception:
            # Unknown, never "flat": a brain reading 0 would think it holds nothing.
            logger.warning("bot watch: the %s position could not be read", symbol, exc_info=True)
            position_qty = None
        items.append(
            {
                "symbol": symbol,
                "halted": bool(snap and snap.get("halted")),
                "halt": snap,
                "last": last,
                "bid": bid,
                "ask": ask,
                "last_update_ts": last_update_ts,
                "volume": volume,
                "position_qty": position_qty,
            }
        )
    view = public_view(row)
    return {
        "symbols": items,
        "at_strategy": [s["id"] for s in view.get("setups") or [] if s.get("effective") == 2],
        "ready": bool(view.get("ready")),
        "live_fire_ready": bool(view.get("ready")),     # LEGACY alias of ``ready``
        "eligible": symbols,
    }
