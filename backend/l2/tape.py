"""
Time & sales (tape) ingest for watched symbols.

Alpaca WS prints are forwarded from main's trade loop via on_alpaca_trade().
Only symbols registered with watch_symbol() are persisted — typically those
with an open depth session or an active signal recording window.
"""
from __future__ import annotations

import logging
import time

from constants import TAPE_SOURCE_ALPACA
from l2 import batch as _batch
from l2.db import get_connection

logger = logging.getLogger(__name__)

_watched: dict[str, str | None] = {}  # symbol -> session_id (optional)


def watch_symbol(symbol: str, session_id: str | None = None) -> None:
    _watched[symbol.upper()] = session_id


def unwatch_symbol(symbol: str) -> None:
    _watched.pop(symbol.upper(), None)


def watched_symbols() -> list[str]:
    return list(_watched.keys())


def is_watched(symbol: str) -> bool:
    return symbol.upper() in _watched


def on_alpaca_trade(
    symbol: str,
    price: float,
    size: float,
    ts: float | None = None,
    exchange: str | None = None,
) -> None:
    """Enqueue a print if the symbol is watched. Never raises."""
    try:
        sym = symbol.upper()
        if sym not in _watched:
            return
        session_id = _watched.get(sym)
        _batch.enqueue_trade((
            sym,
            time.time() if ts is None else ts,
            float(price),
            float(size or 0),
            exchange,
            TAPE_SOURCE_ALPACA,
            session_id,
        ))
    except Exception:
        logger.exception("l2.tape: failed to enqueue trade for %s", symbol)


def get_trades_in_range(symbol: str, start_ts: float, end_ts: float) -> list[dict]:
    _batch.flush()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM tape_trades
            WHERE symbol = ? AND ts >= ? AND ts <= ?
            ORDER BY ts ASC
            """,
            (symbol.upper(), start_ts, end_ts),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def clear_watched_for_tests() -> None:
    _watched.clear()
