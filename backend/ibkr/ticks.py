"""Streaming last-price ticks for open ticker-detail WebSockets.

Level 2 already streams via reqMktDepth/reqMktData. Quote + chart were stuck on
3s snapshot_quotes() polls — this module adds reqMktData last-price updates so
trade_update (and the forming candle) can move on every tick while a detail
panel is open.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from ibkr import client as _client

logger = logging.getLogger(__name__)

BroadcastFn = Callable[..., Awaitable[None]]
FindCacheRowFn = Callable[[str], Optional[dict]]

_Stock = None
_subs: dict[str, dict[str, Any]] = {}
_broadcast: BroadcastFn | None = None
_find_cache_row: FindCacheRowFn | None = None
_subscribe_lock: asyncio.Lock | None = None


def configure(broadcast: BroadcastFn, find_cache_row: FindCacheRowFn) -> None:
    global _broadcast, _find_cache_row
    _broadcast = broadcast
    _find_cache_row = find_cache_row


def _get_lock() -> asyncio.Lock:
    global _subscribe_lock
    if _subscribe_lock is None:
        _subscribe_lock = asyncio.Lock()
    return _subscribe_lock


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


def _on_ticker_update(ticker: Any, symbol: str) -> None:
    sub = _subs.get(symbol)
    if sub is not None:
        # Recorded on every updateEvent (bid/ask/last/volume), not only on a
        # price change below — this is a liveness signal for is_fresh(), so a
        # thinly-traded symbol whose price simply hasn't moved still counts as
        # "streaming fine" and doesn't need the reqTickersAsync backstop.
        sub["last_update_ts"] = time.time()
    if _broadcast is None:
        return
    last = _clean(getattr(ticker, "last", None))
    close = _clean(getattr(ticker, "close", None))
    price = last or close
    if price is None:
        return
    if sub is not None and sub.get("last_price") == price:
        return
    if sub is not None:
        sub["last_price"] = price

    volume = _clean(getattr(ticker, "volume", None))
    vol_i = int(volume) if volume is not None else None
    prev_close = close
    row = _find_cache_row(symbol) if _find_cache_row else None
    if row:
        prev_close = (row.get("previous_close") or row.get("prev_close")) or prev_close
        if vol_i is None and row.get("volume") is not None:
            try:
                vol_i = int(row["volume"])
            except (TypeError, ValueError):
                vol_i = None

    ts = datetime.now(timezone.utc).isoformat()
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_broadcast(symbol, price, None, ts, vol_i, prev_close))
    except RuntimeError:
        logger.debug("IBKR ticks: no running loop to broadcast %s", symbol)


async def subscribe(symbol: str) -> bool:
    """Start (or refcount) a last-price stream for ``symbol``. Returns True if live."""
    symbol = symbol.upper()
    async with _get_lock():
        if symbol in _subs:
            _subs[symbol]["refs"] += 1
            return True
        if not _load_ib_types():
            return False
        ib = _client.get_ib()
        if ib is None:
            return False

        contract = _Stock(symbol, "SMART", "USD")
        try:
            qualified = await ib.qualifyContractsAsync(contract)
            if not qualified:
                logger.warning("IBKR ticks: qualify failed for %s", symbol)
                return False
            contract = qualified[0]
        except Exception as exc:
            logger.warning("IBKR ticks: qualify error for %s: %s", symbol, exc)
            return False

        try:
            ticker = ib.reqMktData(contract, "", False, False)
        except Exception as exc:
            logger.warning("IBKR ticks: reqMktData failed for %s: %s", symbol, exc)
            return False

        def handler(t, sym=symbol):
            _on_ticker_update(t, sym)

        ticker.updateEvent += handler
        _subs[symbol] = {
            "ticker": ticker,
            "contract": contract,
            "handler": handler,
            "refs": 1,
            "last_price": None,
            "last_update_ts": None,
        }
        logger.info("IBKR ticks: subscribed last-price for %s (conId=%s)", symbol, contract.conId)
        return True


async def unsubscribe(symbol: str) -> None:
    symbol = symbol.upper()
    async with _get_lock():
        sub = _subs.get(symbol)
        if not sub:
            return
        sub["refs"] -= 1
        if sub["refs"] > 0:
            return
        ib = _client.get_ib()
        ticker = sub.get("ticker")
        handler = sub.get("handler")
        contract = sub.get("contract")
        if ticker is not None and handler is not None:
            try:
                ticker.updateEvent -= handler
            except (ValueError, AttributeError, KeyError) as exc:
                logger.debug(
                    "IBKR ticks: handler detach failed for %s: %s",
                    symbol,
                    exc,
                )
        if ib is not None and contract is not None:
            try:
                ib.cancelMktData(contract)
            except Exception:
                logger.debug("IBKR ticks: cancelMktData failed for %s", symbol, exc_info=True)
        _subs.pop(symbol, None)
        logger.info("IBKR ticks: unsubscribed %s", symbol)


def subscribed_symbols() -> list[str]:
    return list(_subs.keys())


def is_fresh(symbol: str, max_age_sec: float) -> bool:
    """True if ``symbol`` has a live reqMktData stream that ticked within
    ``max_age_sec``. Used by the detail reprice backstop (ibkr/reprice.py) to
    skip a redundant reqTickersAsync snapshot when the stream is already
    delivering — false before the first tick arrives or once ticks stop."""
    sub = _subs.get(symbol.upper())
    if sub is None:
        return False
    last_ts = sub.get("last_update_ts")
    if last_ts is None:
        return False
    return (time.time() - last_ts) <= max_age_sec
