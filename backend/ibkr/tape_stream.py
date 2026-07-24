"""
IBKR tick-by-tick Time & Sales stream.

Uses reqTickByTickData("AllLast") — every print as it appears in the TWS
Time & Sales window. One stream per open symbol, refcounted like depth.py.

IB limitation: no second reqTickByTickData for the same instrument within
15 seconds. The 15s debounce tracks when we last cancelled a subscription
and refuses to resubscribe until the window clears.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any

from constants import (
    IBKR_ERROR_TICK_BY_TICK_CODES,
    IBKR_TAPE_TICK_TYPE,
)
from ibkr import client as _client
from ibkr import depth as _depth
from ibkr.tape_side import best_bid_ask, classify_print_side
from metrics.op_metrics import timed_sync

logger = logging.getLogger(__name__)

_Stock = None
_contracts: dict[str, Any] = {}
_tickers: dict[str, Any] = {}
_queues: dict[str, asyncio.Queue] = {}
_ws_viewers: dict[str, int] = {}
# Unix time when we last cancelled a symbol's tick-by-tick subscription.
_cancelled_at: dict[str, float] = {}
_error_hooked_ib_ids: set[int] = set()

IBKR_TAPE_RESUBSCRIBE_GUARD_SEC = 16.0  # IB requires 15s gap; add 1s margin
IBKR_TAPE_QUEUE_MAXSIZE = 2048          # cap buffer per symbol
TAPE_STREAM_HEARTBEAT_SEC = 15.0        # yield None when no prints arrive


def _load_ib_types() -> bool:
    global _Stock
    if _Stock is not None:
        return True
    try:
        from ib_async import Stock
        _Stock = Stock
        return True
    except ImportError:
        return False


def _clean(x: float | None) -> float | None:
    if x is None:
        return None
    try:
        return None if math.isnan(x) else float(x)
    except TypeError:
        return None


def _push_queue(symbol: str, payload: dict) -> None:
    q = _queues.get(symbol)
    if q is None:
        return
    try:
        q.put_nowait(payload)
    except asyncio.QueueFull:
        try:
            q.get_nowait()
            q.put_nowait(payload)
        except asyncio.QueueEmpty:
            logger.debug("IBKR tape: queue empty after full for %s", symbol)
        except asyncio.QueueFull:
            logger.warning("IBKR tape: queue still full for %s after drop", symbol)


def _on_tape_update(ticker: Any, symbol: str) -> None:
    """Called on every updateEvent for the tick-by-tick ticker."""
    tbt_list = getattr(ticker, "tickByTicks", None)
    if not tbt_list:
        return
    for tbt in tbt_list:
        ts = getattr(tbt, "time", None)
        if ts is None:
            ts_iso = datetime.now(timezone.utc).isoformat()
        elif hasattr(ts, "isoformat"):
            ts_iso = ts.isoformat()
        else:
            ts_iso = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()

        price = _clean(getattr(tbt, "price", None))
        size = _clean(getattr(tbt, "size", None))
        # IB sends sentinel empties; skip non-positive prices.
        if price is None or price <= 0:
            continue

        exchange = getattr(tbt, "exchange", None) or ""
        conditions = getattr(tbt, "specialConditions", None) or ""

        # Classify against the open symbol's live BBO (depth / L1). Never use
        # another symbol's book — current_book is keyed by the tape symbol.
        bid, ask = best_bid_ask(_depth.current_book(symbol))
        side = classify_print_side(price, bid, ask)

        size_i = int(size) if size is not None else 0
        _push_queue(
            symbol,
            {
                "type": "print",
                "symbol": symbol,
                "time": ts_iso,
                "price": price,
                "size": size_i,
                "exchange": exchange,
                "conditions": conditions,
                "side": side,
                "bid": bid,
                "ask": ask,
            },
        )
        # P6 — durable local archive (non-fatal if archive package fails)
        try:
            from archive.capture import parse_iso_to_unix, record_tape_print
            from constants import ARCHIVE_SOURCE_IBKR

            print_ts = parse_iso_to_unix(ts_iso)
            record_tape_print(
                symbol=symbol,
                ts=print_ts,
                price=price,
                size=float(size_i),
                exchange=exchange,
                conditions=conditions,
                side=side,
                bid=bid,
                ask=ask,
                receive_ts=time.time(),
                source=ARCHIVE_SOURCE_IBKR,
            )
            # 1m OHLCV for archive/replay (same IBKR tape source — not Alpaca).
            from archive.bar_builder import on_tape_print

            on_tape_print(
                symbol=symbol,
                ts=print_ts,
                price=price,
                size=float(size_i),
                source=ARCHIVE_SOURCE_IBKR,
            )
        except Exception:
            logger.exception("IBKR tape: archive.record_tape_print failed for %s", symbol)

    # Clear consumed ticks to avoid re-processing on next updateEvent
    try:
        tbt_list.clear()
    except (AttributeError, TypeError) as exc:
        logger.debug("IBKR tape: could not clear tick list for %s: %s", symbol, exc)


def _install_error_hook(ib: Any) -> None:
    if id(ib) in _error_hooked_ib_ids:
        return
    ib.errorEvent += _on_ib_error
    _error_hooked_ib_ids.add(id(ib))


def _on_ib_error(reqId: int, errorCode: int, errorString: str, contract: Any) -> None:
    if errorCode not in IBKR_ERROR_TICK_BY_TICK_CODES:
        return
    con_id = getattr(contract, "conId", None) if contract is not None else None
    if con_id is None:
        return
    for sym, c in list(_contracts.items()):
        if getattr(c, "conId", None) != con_id:
            continue
        msg = errorString or f"Tick-by-tick rejected (IB error {errorCode})"
        logger.warning("IBKR tape: subscription error for %s — %s: %s", sym, errorCode, msg)
        _push_queue(sym, {"type": "error", "symbol": sym, "message": msg})
        return


async def subscribe_async(symbol: str) -> dict:
    """Subscribe to tick-by-tick AllLast for a symbol.

    Returns {"ok": True/False, "error": None/"..."}.
    Safe to call multiple times — idempotent once subscribed.
    """
    symbol = symbol.upper()
    ib = _client.get_ib()
    if ib is None:
        return {"ok": False, "error": "IBKR not connected"}
    if not _load_ib_types():
        return {"ok": False, "error": "ib_async not available"}

    if symbol in _tickers:
        return {"ok": True, "error": None}

    # IB 15-second same-instrument guard
    last_cancel = _cancelled_at.get(symbol, 0)
    wait_remaining = IBKR_TAPE_RESUBSCRIBE_GUARD_SEC - (time.time() - last_cancel)
    if wait_remaining > 0:
        logger.debug(
            "IBKR tape: %s resubscribe guard active (%.1fs remaining)", symbol, wait_remaining
        )
        return {"ok": False, "error": f"Resubscribing in {wait_remaining:.0f}s — please wait"}

    contract = _Stock(symbol, "SMART", "USD")
    try:
        qualified = await ib.qualifyContractsAsync(contract)
    except Exception as exc:
        logger.exception("IBKR tape: qualify failed for %s: %s", symbol, exc)
        return {"ok": False, "error": str(exc)}

    if not qualified:
        return {"ok": False, "error": f"Could not qualify contract for {symbol}"}

    contract = qualified[0]
    _contracts[symbol] = contract
    _queues[symbol] = asyncio.Queue(maxsize=IBKR_TAPE_QUEUE_MAXSIZE)
    _install_error_hook(ib)

    try:
        with timed_sync("ibkr.tape.subscribe"):
            ticker = ib.reqTickByTickData(
                contract, IBKR_TAPE_TICK_TYPE, numberOfTicks=0, ignoreSize=False,
            )
        def handler(t, sym=symbol):
            _on_tape_update(t, sym)

        ticker.updateEvent += handler
        _tickers[symbol] = {"ticker": ticker, "handler": handler}
        logger.info("IBKR tape: subscribed %s (AllLast)", symbol)
    except Exception as exc:
        logger.exception("IBKR tape: reqTickByTickData failed for %s: %s", symbol, exc)
        _contracts.pop(symbol, None)
        _queues.pop(symbol, None)
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "error": None}


def unsubscribe(symbol: str) -> None:
    symbol = symbol.upper()
    sub = _tickers.pop(symbol, None)
    contract = _contracts.pop(symbol, None)
    _queues.pop(symbol, None)
    if sub is None:
        return
    ib = _client.get_ib()
    ticker = sub.get("ticker")
    handler = sub.get("handler")
    if ticker and handler:
        try:
            ticker.updateEvent -= handler
        except (ValueError, AttributeError, KeyError) as exc:
            logger.debug(
                "IBKR tape: handler detach failed for %s: %s",
                symbol,
                exc,
            )
    if ib and contract is not None:
        try:
            ib.cancelTickByTickData(contract, IBKR_TAPE_TICK_TYPE)
        except Exception as exc:
            logger.debug(
                "IBKR tape: cancelTickByTickData failed for %s: %s",
                symbol,
                exc,
            )
    _cancelled_at[symbol] = time.time()
    logger.info("IBKR tape: unsubscribed %s", symbol)


def ws_viewer_opened(symbol: str) -> None:
    _ws_viewers[symbol] = _ws_viewers.get(symbol, 0) + 1


def ws_viewer_closed(symbol: str) -> bool:
    remaining = _ws_viewers.get(symbol, 0) - 1
    if remaining <= 0:
        _ws_viewers.pop(symbol, None)
        return True
    _ws_viewers[symbol] = remaining
    return False


def viewer_count(symbol: str) -> int:
    return _ws_viewers.get(symbol, 0)


def has_queue(symbol: str) -> bool:
    return symbol in _queues


async def stream(symbol: str):
    """AsyncGenerator yielding print dicts (or None on heartbeat timeout)."""
    q = _queues.get(symbol)
    if q is None:
        return
    while True:
        try:
            print_data = await asyncio.wait_for(q.get(), timeout=TAPE_STREAM_HEARTBEAT_SEC)
            yield print_data
        except asyncio.TimeoutError:
            yield None
