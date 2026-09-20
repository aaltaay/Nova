"""Sim market projections; captured data never falls through to fabricated facts.

ADR 001 extracts read views from the synthetic tape state owner. ADR 017 keeps
these projections as capture compatibility, not another replay engine.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from constants_sim import (
    SIM_BOOK_LEVELS, SIM_BOOK_SIZE, SIM_BOOK_TICK, SIM_EXCHANGE,
    SIM_PRINT_SIZE, SIM_START_LAST, SIM_SYMBOL,
)
from sim import session_clock as _clock


def _capture_intent() -> bool:
    from sim import replay
    state = replay.status_payload()
    return state["replay_source"] != "synthetic" or not state["replay_ok"]


def quote(symbol: str | None = None) -> dict[str, Any] | None:
    from sim import market, capture_player, replay
    if _capture_intent():
        if not replay.is_capture_replay():
            return None
        selected = capture_player.snapshot()
        if selected is None or (symbol and symbol.strip().upper() != selected.symbol):
            return None
        return capture_player.quote_at(state=selected)
    sym = (symbol or SIM_SYMBOL).strip().upper()
    if sym != SIM_SYMBOL:
        return None
    px, prev = market.last(), market.prev_close()
    change = px - prev
    return {"symbol": SIM_SYMBOL, "last": px, "bid": market.bid(), "ask": market.ask(),
            "prev_close": prev, "volume": market.volume(), "change_abs": round(change, 4),
            "change_pct": round(change / prev, 6) if prev else 0.0}


def last_quotes(symbols: list[str] | None = None) -> dict[str, dict[str, Any]]:
    from sim import market, capture_player
    selected = capture_player.snapshot() if _capture_intent() else None
    symbol = selected.symbol if selected else SIM_SYMBOL
    wanted = {str(s).strip().upper() for s in symbols if s} if symbols is not None else None
    if wanted is not None and symbol not in wanted:
        return {}
    row = quote(symbol)
    if row is None:
        return {}
    return {symbol: {"price": row["last"], "last_update_ts": market._now_iso(),
                     "owners": {"capture" if selected else "sim"}, "volume": row.get("volume")}}


def book() -> dict[str, Any]:
    from sim import market, capture_player, replay
    if _capture_intent():
        return (capture_player.book_at() or {}) if replay.is_capture_replay() else {}
    b = market.bid()
    a = market.ask()
    mult = _clock.phase_volume_mult()
    bids = [
        {
            "price": round(b - i * SIM_BOOK_TICK, 4),
            "size": float(SIM_BOOK_SIZE * (SIM_BOOK_LEVELS - i) * mult),
            "side": "bid",
            "mm": "SIM",
        }
        for i in range(SIM_BOOK_LEVELS)
    ]
    asks = [
        {
            "price": round(a + i * SIM_BOOK_TICK, 4),
            "size": float(SIM_BOOK_SIZE * (SIM_BOOK_LEVELS - i) * mult),
            "side": "ask",
            "mm": "SIM",
        }
        for i in range(SIM_BOOK_LEVELS)
    ]
    return {"bids": bids, "asks": asks, "l1_fallback": False}


def ticker_snapshot(symbol: str) -> dict[str, Any]:
    from sim import market, capture_player, replay
    if _capture_intent():
        selected = capture_player.snapshot() if replay.is_capture_replay() else None
        if selected is None or symbol.strip().upper() != selected.symbol:
            return {}
        row = capture_player.quote_at(state=selected)
        return _capture_ticker_snapshot(row, selected) if row is not None else {}
    q = market.quote(symbol)
    if q is None:
        return {}
    now = market._now_iso()
    last = q.get("last")
    prev = q.get("prev_close")
    if prev is None:
        prev = last
    return {
        "latest_trade": {
            "price": last,
            "size": SIM_PRINT_SIZE,
            "exchange": SIM_EXCHANGE,
            "timestamp": now,
        },
        "latest_quote": {"bid": q.get("bid"), "ask": q.get("ask"), "timestamp": now},
        "minute_bar": None,
        "daily_bar": {
            "open": SIM_START_LAST,
            "high": market._high if market._high else last,
            "low": market._low if market._low else last,
            "close": last,
            "volume": market.volume(),
            "trade_count": None,
            "vwap": None,
            "timestamp": now,
        },
        "prev_daily_bar": {
            "open": None,
            "high": None,
            "low": None,
            "close": prev,
            "volume": None,
            "trade_count": None,
            "vwap": None,
            "timestamp": None,
        },
        "prev_close": prev,
        "session_close": prev,
        "session_prev_close": None,
        "source": q.get("source") or "sim",
    }


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
