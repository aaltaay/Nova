"""A quote from a market-data line held for a moment (ADR 053 amendment 2026-10-13).

IBKR's snapshot answers only at its snapshot end -- about 11 s a batch for a future, an index or NYSE's
indicators, and for stocks outside the session (measured 2026-10-13) -- so the Market page opens a streaming line,
takes IBKR's first ticks and cancels it. At most ``MARKET_STREAM_BATCH`` lines are open at once, each for at most
``MARKET_STREAM_WAIT_SEC``.

A line someone else holds is never cancelled. A contract that already has a subscription is read from its ticker;
a line that gained a listener while it was open (the desk subscribed the same contract, and ib_async answered with
this line's ticker) is left open for that listener. ib_async keeps one ticker per contract for the life of the
connection, prices included, so a line this read opens starts from a cleared ticker: a price it returns came from
this line, never from the last read of the same contract. Must run on the IB loop.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from constants_market_board import (
    MARKET_STREAM_BATCH,
    MARKET_STREAM_POLL_SEC,
    MARKET_STREAM_SETTLE_SEC,
    MARKET_STREAM_WAIT_SEC,
)

logger = logging.getLogger(__name__)
# The ticker fields a read uses, cleared when this read opens the contract's only line.
_PRICE_FIELDS = ("last", "lastSize", "bid", "bidSize", "ask", "askSize", "close", "open", "high", "low", "volume")


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def priced(ticker: Any) -> bool:
    """A print, or both sides of the quote (NYSE's AD and VOL indicators carry their counts as bid and ask)."""
    if _num(getattr(ticker, "last", None)) is not None:
        return True
    bid, ask = _num(getattr(ticker, "bid", None)), _num(getattr(ticker, "ask", None))
    return bid is not None and ask is not None and bid > 0 and ask > 0


def complete(ticker: Any) -> bool:
    return priced(ticker) and _num(getattr(ticker, "close", None)) is not None


def _held_by_another(ib: Any, contract: Any) -> Any | None:
    """The ticker of a line already open on ``contract`` (the desk's), else ``None``."""
    registry = getattr(getattr(ib, "wrapper", None), "subscriptions", None)
    find = getattr(registry, "find_market_data", None)
    if find is None:
        return None
    sub = find(getattr(contract, "conId", 0), "mktData")
    return getattr(sub, "ticker", None) if sub is not None else None


def _clear(ticker: Any) -> None:
    for name in _PRICE_FIELDS:
        try:
            setattr(ticker, name, math.nan)
        except (AttributeError, TypeError):  # maintainer: allow-swallow a field this ticker type lacks stays unread
            pass


def _listeners(ticker: Any) -> int:
    try:
        return len(ticker.updateEvent)
    except (AttributeError, TypeError):
        return 0


async def _settle(tickers: list[Any]) -> None:
    """Until every ticker is complete, or every one is priced and the settle time passed, or the deadline."""
    clock = asyncio.get_running_loop()
    deadline = clock.time() + MARKET_STREAM_WAIT_SEC
    priced_at: float | None = None
    while True:
        now = clock.time()
        if all(complete(t) for t in tickers):
            return
        if priced_at is None and all(priced(t) for t in tickers):
            priced_at = now
        if now >= deadline or (priced_at is not None and now - priced_at >= MARKET_STREAM_SETTLE_SEC):
            return
        await asyncio.sleep(MARKET_STREAM_POLL_SEC)


async def _batch(ib: Any, contracts: list[Any]) -> dict[int, Any]:
    tickers: dict[int, Any] = {}
    opened: list[tuple[Any, Any, int]] = []   # (contract, ticker, listeners when this read opened it)
    try:
        for contract in contracts:
            held = _held_by_another(ib, contract)
            if held is not None:
                tickers[contract.conId] = held
                continue
            ticker = ib.reqMktData(contract, "", False, False)
            _clear(ticker)   # no other line feeds it (checked above, with no await between): only this line's ticks
            tickers[contract.conId] = ticker
            opened.append((contract, ticker, _listeners(ticker)))
        await _settle(list(tickers.values()))
    finally:
        for contract, ticker, before in opened:
            if _listeners(ticker) > before:
                logger.info("market_board: left %s's line open -- it gained a listener during the read",
                            getattr(contract, "localSymbol", None) or getattr(contract, "symbol", "?"))
                continue
            try:
                ib.cancelMktData(contract)
            except Exception:  # noqa: BLE001 -- a line that will not cancel is said, never raised into the read
                logger.warning("market_board: cancelling %s's line failed", getattr(contract, "symbol", "?"),
                               exc_info=True)
    return tickers


async def read(ib: Any, contracts: list[Any]) -> dict[int, Any]:
    """``{conId: ticker}`` for every contract, ``MARKET_STREAM_BATCH`` lines at a time.

    A ticker may hold no price: IBKR sent none before ``MARKET_STREAM_WAIT_SEC``. Read its fields at once -- a
    cancelled line's ticker is not updated again, and a borrowed one keeps moving.
    """
    out: dict[int, Any] = {}
    for i in range(0, len(contracts), MARKET_STREAM_BATCH):
        out.update(await _batch(ib, contracts[i:i + MARKET_STREAM_BATCH]))
    return out
