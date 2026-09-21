"""Sim market projections of a loaded capture; nothing is ever fabricated.

ADR 001 extracts read views from the capture player. ADR 017 keeps these
projections as capture compatibility, not another replay engine. With no
capture loaded every view is empty -- there is no synthetic instrument.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _selected(symbol: str | None = None):
    from sim import capture_player, replay

    if not replay.is_capture_replay():
        return None
    selected = capture_player.snapshot()
    if selected is None or (symbol and symbol.strip().upper() != selected.symbol):
        return None
    return selected


def quote(symbol: str | None = None) -> dict[str, Any] | None:
    from sim import capture_player

    selected = _selected(symbol)
    return capture_player.quote_at(state=selected) if selected is not None else None


def last_quotes(symbols: list[str] | None = None) -> dict[str, dict[str, Any]]:
    from sim import market

    selected = _selected()
    if selected is None:
        return {}
    wanted = {str(s).strip().upper() for s in symbols if s} if symbols is not None else None
    if wanted is not None and selected.symbol not in wanted:
        return {}
    row = quote(selected.symbol)
    if row is None:
        return {}
    return {selected.symbol: {"price": row["last"], "last_update_ts": market._now_iso(),
                              "owners": {"capture"}, "volume": row.get("volume")}}


def book() -> dict[str, Any]:
    from sim import capture_player

    selected = _selected()
    return (capture_player.book_at(state=selected) or {}) if selected is not None else {}


def ticker_snapshot(symbol: str) -> dict[str, Any]:
    from sim import capture_player

    selected = _selected(symbol)
    if selected is None:
        return {}
    row = capture_player.quote_at(state=selected)
    return _capture_ticker_snapshot(row, selected) if row is not None else {}


def _capture_ticker_snapshot(row: dict, selected) -> dict:
    from sim import capture_player
    reached = capture_player.recent_prints(1, state=selected)
    trade = reached[-1] if reached else None
    timestamp = datetime.fromtimestamp(row["ts"], timezone.utc).isoformat()
    quote_known = row.get("bid") is not None or row.get("ask") is not None
    previous = row.get("prev_close")
    return {
        "latest_trade": ({"price": trade["price"], "size": trade["size"],
                          "exchange": trade["exchange"], "timestamp": trade["time"]} if trade else None),
        "latest_quote": ({"bid_price": row.get("bid"), "ask_price": row.get("ask"),
                          "bid_size": row.get("bid_size"), "ask_size": row.get("ask_size"),
                          "bid": row.get("bid"), "ask": row.get("ask"), "timestamp": timestamp}
                         if quote_known else None),
        "minute_bar": None, "daily_bar": None, "prev_daily_bar": None,
        "prev_close": previous, "session_close": previous, "session_prev_close": None,
        "source": "capture",
    }
