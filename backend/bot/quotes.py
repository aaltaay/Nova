"""Shared-feed quotes. Never opens a private reqMktData.

On a Sim replay (ADR 052) the bot's last, bid and ask are the loaded replay's at the playhead
(``sim.practice.reference``) -- what its practice orders fill against -- for a Session Record and a
historical window alike."""
from __future__ import annotations

from typing import Any

from ibkr.tape_side import best_bid_ask


def _replay(sym: str) -> dict[str, Any] | None:
    from bot.replay_desk import quote

    return quote(sym)


def last_quote(symbol: str) -> dict[str, Any] | None:
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    replayed = _replay(sym)
    if replayed is not None:
        return {"price": replayed["last"]} if replayed["last"] is not None else None
    from ibkr import ticks as _ticks

    return _ticks.last_quotes([sym]).get(sym)


def top_of_book(symbol: str) -> tuple[float | None, float | None]:
    sym = (symbol or "").strip().upper()
    if not sym:
        return None, None
    replayed = _replay(sym)
    if replayed is not None:
        return replayed["bid"], replayed["ask"]
    try:
        from ibkr.depth import state as _depth

        book = _depth.current_book(sym)
    except Exception:
        book = None
    return best_bid_ask(book)


def eyes_row(symbol: str) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()
    last = last_quote(sym) or {}
    bid, ask = top_of_book(sym)
    return {
        "symbol": sym,
        "last": last.get("price"),
        "last_update_ts": last.get("last_update_ts"),
        "bid": bid,
        "ask": ask,
        "volume": last.get("volume"),
        "has_l1": bool(last),
        "has_depth": bid is not None or ask is not None,
    }
