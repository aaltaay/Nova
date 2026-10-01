"""Trial T1's tape reading for the trade you hold (ADR 036 amendment 2026-10-01, ADR 041).

The flow score (``setup_scanner.tape_flow``) with a 30 s window and every other number the default, over
the sensor rings the desk already fills: no IBKR line is opened and nothing waits. The Trader reads it
every ``STOCK_READ_FLUSH_POLL_MS`` while you hold, and calls SELL NOW · FLUSH "in trial" on a flush. It is
a call in trial, never an order: trial T1 decides whether it ever is one.
"""
from __future__ import annotations

from typing import Any

from constants_stock_read import STOCK_READ_FLUSH_SCHEMA_VERSION, STOCK_READ_FLUSH_WINDOW_SEC
from setup_scanner import tape_flow


def reading(symbol: str, now: float) -> dict[str, Any]:
    """``{schema_version, symbol, at, score, label, window_sec}``; ``blind`` with nothing in the rings."""
    from sensors import rings

    prints = rings.recent_prints(symbol)
    books = [(float(b.get("ts") or 0), b) for b in rings.recent_books(symbol)]
    since = min((float(p["ts"]) for p in prints if isinstance(p.get("ts"), (int, float))), default=None)
    params = tape_flow.FlowParams(window_sec=STOCK_READ_FLUSH_WINDOW_SEC)
    flow = tape_flow.evaluate(now=now, books=books, prints=prints, p=params, history_from=since)
    return {"schema_version": STOCK_READ_FLUSH_SCHEMA_VERSION, "symbol": symbol, "at": now,
            "score": flow.get("score"), "label": flow.get("label"), "window_sec": STOCK_READ_FLUSH_WINDOW_SEC}
