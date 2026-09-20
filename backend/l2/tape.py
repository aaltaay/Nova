"""
Time & sales (tape) ingest for watched symbols.

IBKR AllLast prints arrive through the independent bounded recording worker.
Only symbols registered with watch_symbol() are persisted — typically those
with an open depth session or an active signal recording window.
"""

from __future__ import annotations

import logging
import time

from l2 import batch as _batch
from l2.db import get_connection

logger = logging.getLogger(__name__)

_watched: dict[str, str | None] = {}  # symbol -> session_id (optional)
_started: dict[str, float] = {}
_written: dict[str, float] = {}
_warned: dict[str, str] = {}


def watch_symbol(symbol: str, session_id: str | None = None) -> None:
    _watched[symbol.upper()] = session_id
    _started[symbol.upper()] = time.time()
    _written.pop(symbol.upper(), None)
    _warned.pop(symbol.upper(), None)


def unwatch_symbol(symbol: str) -> None:
    _watched.pop(symbol.upper(), None)
    _started.pop(symbol.upper(), None)
    _written.pop(symbol.upper(), None)
    _warned.pop(symbol.upper(), None)


def watched_symbols() -> list[str]:
    return list(_watched.keys())


def is_watched(symbol: str) -> bool:
    return symbol.upper() in _watched


def on_alpaca_trade(*args, **kwargs) -> None:
    """Retired compatibility entry; Alpaca is never a recording source."""
    logger.warning("l2.tape: rejected retired Alpaca trade input")


def on_trade_print(symbol, price, size, ts, exchange=None) -> None:
    """Synchronous worker/test adapter for the IBKR source."""
    if is_watched(symbol):
        persist_print(
            {
                "symbol": symbol.upper(),
                "price": price,
                "size": size,
                "ts": ts,
                "exchange": exchange,
                "source": "ibkr",
                "session_id": session_id(symbol),
                "conditions": "",
                "receive_ts": time.time(),
            }
        )


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
    _started.clear()
    _written.clear()
    _warned.clear()


def session_id(symbol: str) -> str | None:
    return _watched.get(symbol.upper())


def watch_started(symbol: str) -> float | None:
    return _started.get(symbol.upper())


def persist_print(payload) -> None:
    """Worker-only durable write; raise failures to the sink health contract."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO tape_trades "
            "(symbol, ts, price, size, exchange, source, session_id, conditions, receive_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(
                payload.get(key)
                for key in (
                    "symbol",
                    "ts",
                    "price",
                    "size",
                    "exchange",
                    "source",
                    "session_id",
                    "conditions",
                    "receive_ts",
                )
            ),
        )
        conn.commit()
        symbol = payload["symbol"]
        if symbol in _watched and payload.get("watch_started") == _started.get(symbol):
            _written[symbol] = time.time()
    finally:
        conn.close()


def health() -> dict:
    from capture.bridge_ibkr import producer_health
    from ibkr.tape_recording import l2_sink, dispatch_errors
    from ibkr.constants_tape_recording import TAPE_RECORD_STALE_SEC

    writer = l2_sink.status()
    writer["error"] = writer["error"] or dispatch_errors.get("l2")
    symbols = {symbol: producer_health(symbol) for symbol in watched_symbols()}
    for symbol, state in symbols.items():
        last = _written.get(symbol)
        overdue = time.time() - (last or _started.get(symbol, time.time())) > TAPE_RECORD_STALE_SEC
        state["last_write_ts"] = last
        if not last or overdue:
            state["healthy"] = False
            state["sink_state"] = "stale" if overdue else "waiting"
        if overdue and _warned.get(symbol) != "stale":
            logger.warning("L2 tape: no recent persisted prints for watched %s", symbol)
            _warned[symbol] = "stale"
        elif not overdue:
            _warned.pop(symbol, None)
    return {
        "healthy": not writer["error"] and all(s["healthy"] for s in symbols.values()),
        "writer": writer,
        "symbols": symbols,
    }


def audit_coverage() -> dict:
    """Count past depth sessions with no tape in their observed time interval."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            WITH windows AS (
                SELECT COALESCE(session_id, recording_id) AS session, symbol,
                       MIN(ts) AS start_ts, MAX(ts) AS end_ts, COUNT(*) AS snapshots
                FROM l2_snapshots GROUP BY COALESCE(session_id, recording_id), symbol
            )
            SELECT *, EXISTS(SELECT 1 FROM tape_trades t WHERE t.symbol = w.symbol
                AND t.ts BETWEEN w.start_ts AND w.end_ts) AS has_tape
            FROM windows w
        """).fetchall()
        missing = [dict(row) for row in rows if not row["has_tape"]]
        return {
            "depth_sessions": len(rows),
            "sessions_without_tape": len(missing),
            "missing": missing,
            "note": "No tape does not prove a feed failure; intervals can be quiet. Past missing prints cannot be reconstructed.",
        }
    finally:
        conn.close()
