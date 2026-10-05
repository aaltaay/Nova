"""What the Trader's quote socket (``/ws/ticker/{symbol}``) is pushed: trade and halt updates (ADR 045).

Moved out of ``websocket.py`` (the Alpaca stream) with the quote's version: every ``trade_update``
carries the symbol's quote ``seq`` / ``at`` (``market_view.versions``), so an order can say which
quote the screen showed and the gate can tell how old it was.
"""
from __future__ import annotations

import json
import logging

from market_view import versions
from ticker import _ticker_ws_clients

logger = logging.getLogger(__name__)


async def broadcast_halt_update(sym: str, halt: dict | None) -> None:
    """Push ticker.halted state to ticker-detail WS clients (L2 HaltEtaChip)."""
    clients = _ticker_ws_clients.get(sym)
    if not clients:
        return
    payload = json.dumps({
        "type": "halt_update",
        "symbol": sym,
        "halt": halt,
    })
    dead: list = []
    for ws in list(clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


TRADE_UPDATE_SOURCE_STREAM = "stream"      # a print from the live trade stream
TRADE_UPDATE_SOURCE_SNAPSHOT = "snapshot"  # a Level 1 quote snapshot -- a last price, not a print
TRADE_UPDATE_SOURCE_SIM = "sim"            # a replayed recorded print


async def broadcast_trade_update(
    sym: str,
    price: float,
    size: int | None,
    timestamp: str | None,
    volume: int | None = None,
    prev_close: float | None = None,
    source: str = TRADE_UPDATE_SOURCE_STREAM,
    *,
    seq: int | None = None,
    at: float | None = None,
) -> None:
    """Push a lightweight trade update to ticker-detail WS clients watching this symbol.

    ``source`` says what the price is. A ``snapshot`` is IBKR's Level 1 last at
    the moment of the request -- after the close that can be the regular
    session's last while the tape trades elsewhere -- so it may update the
    quote box but must never paint a candle (QA 2026-09-22: a $6.9 stock grew
    a 10-second wick to $4 that no exchange printed).

    ``seq`` / ``at`` are the quote's version (ADR 045): the IBKR stream takes it when Nova
    applied the update; any other caller gets the next one now.
    """
    if seq is None:
        version = versions.bump(versions.QUOTE, sym)
        seq, at = version.seq, version.at
    clients = _ticker_ws_clients.get(sym)
    if not clients:
        return
    payload_obj: dict = {
        "type": "trade_update",
        "symbol": sym,
        "price": price,
        "size": size,
        "timestamp": timestamp,
        "volume": volume,
        "source": source,
        "seq": seq,
        "at": at,
    }
    if prev_close is not None:
        payload_obj["prev_close"] = prev_close
    payload = json.dumps(payload_obj)
    dead: list = []
    for ws in list(clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)
