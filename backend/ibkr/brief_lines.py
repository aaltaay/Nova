"""A quote from a market-data line held for a moment (ADR 054; first the Market page's, ADR 053 amendment 2026-10-13).

IBKR's snapshot answers only at its snapshot end -- about 11 s a batch for a future, an index or NYSE's
indicators, and for stocks outside the session (measured 2026-10-13) -- so a quote someone waits on opens a
streaming line, takes IBKR's first ticks and cancels it. At most ``IBKR_BRIEF_LINE_BATCH`` lines are open at once,
every reader together, each for at most ``IBKR_BRIEF_LINE_WAIT_SEC``, and none opens with fewer than
``IBKR_BRIEF_MIN_FREE_LINES`` lines
spare beyond Nova's own reserve (``NoHeadroom``). Readers: the Market page, the Cryptos page's bridge stocks, the
Trader's quote head when nothing else has a price, and the ticker-detail backstop.

A line someone else holds is never cancelled. A contract that already has a subscription is read from its ticker
(no line opened, no headroom needed); a line that gained a listener while it was open (the desk subscribed the same
contract, and ib_async answered with this line's ticker) is left open for that listener. A stock's line asks the
desk's own generic ticks (``IBKR_L1_GENERIC_TICKS``), so that listener gets the line it would have opened. ib_async
keeps one ticker per contract for the life of the connection, prices included, so a line this read opens starts
from a cleared ticker: a price it returns came from this line, never from the last read of the same contract.
``read`` must run on the IB loop; ``stock_quotes`` hops there itself.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from constants_ibkr import (
    IBKR_BRIEF_LINE_BATCH,
    IBKR_BRIEF_LINE_POLL_SEC,
    IBKR_BRIEF_LINE_SETTLE_SEC,
    IBKR_BRIEF_LINE_WAIT_SEC,
    IBKR_BRIEF_MIN_FREE_LINES,
    IBKR_DISCOVERY_QUALIFY_TIMEOUT_SEC,
    IBKR_L1_GENERIC_TICKS,
    IBKR_L1_STREAM_RESERVE,
)
from metrics.op_metrics import timed

logger = logging.getLogger(__name__)
# The ticker fields a read uses, cleared when this read opens the contract's only line.
_PRICE_FIELDS = ("last", "lastSize", "bid", "bidSize", "ask", "askSize", "close", "open", "high", "low", "volume")
# Brief lines open now, every reader together (IB loop only). The cold slot let one snapshot batch run at a time;
# brief reads run side by side, so this keeps their sum at IBKR_BRIEF_LINE_BATCH. ``spare_lines`` counts only the
# desk's own lines and cannot see them.
_lines_open = 0


class NoHeadroom(Exception):
    """Too few market-data lines are spare: the read waits rather than compete with the desk."""


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def priced(ticker: Any, *, prints: bool = False) -> bool:
    """A print; without ``prints`` also both sides of the quote (NYSE's AD and VOL indicators carry their counts
    as bid and ask). A stock's quote can arrive before its last trade, so a stock read waits for the print."""
    if _num(getattr(ticker, "last", None)) is not None:
        return True
    if prints:
        return False
    bid, ask = _num(getattr(ticker, "bid", None)), _num(getattr(ticker, "ask", None))
    return bid is not None and ask is not None and bid > 0 and ask > 0


def complete(ticker: Any, *, prints: bool = False) -> bool:
    return priced(ticker, prints=prints) and _num(getattr(ticker, "close", None)) is not None


# -- headroom ----------------------------------------------------------------------------------------------------
def free_lines() -> int | None:
    try:
        from ibkr import ticks

        return int(ticks.ticker_budget_status()["reqMktData_remaining"])
    except Exception:  # noqa: BLE001 -- unknown budget: the read runs as the desk's own reads do
        return None


def spare_lines() -> int | None:
    """Lines free beyond Nova's own reserve for an opening Trader tab; ``None`` when unknown."""
    free = free_lines()
    return None if free is None else free - int(IBKR_L1_STREAM_RESERVE)


def headroom_ok() -> bool:
    spare = spare_lines()
    return spare is None or spare >= IBKR_BRIEF_MIN_FREE_LINES


def guard() -> None:
    """Raise ``NoHeadroom`` while fewer than ``IBKR_BRIEF_MIN_FREE_LINES`` lines are spare."""
    spare = spare_lines()
    if spare is not None and spare < IBKR_BRIEF_MIN_FREE_LINES:
        raise NoHeadroom(f"{max(spare, 0)} market-data lines spare ({IBKR_BRIEF_MIN_FREE_LINES} needed to read)")


# -- the read ----------------------------------------------------------------------------------------------------
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


async def _settle(tickers: list[Any], prints: bool) -> None:
    """Until every ticker is complete, or every one is priced and the settle time passed, or the deadline."""
    clock = asyncio.get_running_loop()
    deadline = clock.time() + IBKR_BRIEF_LINE_WAIT_SEC
    priced_at: float | None = None
    while True:
        now = clock.time()
        if all(complete(t, prints=prints) for t in tickers):
            return
        if priced_at is None and all(priced(t, prints=prints) for t in tickers):
            priced_at = now
        if now >= deadline or (priced_at is not None and now - priced_at >= IBKR_BRIEF_LINE_SETTLE_SEC):
            return
        await asyncio.sleep(IBKR_BRIEF_LINE_POLL_SEC)


def _name(contract: Any) -> str:
    return getattr(contract, "localSymbol", None) or getattr(contract, "symbol", None) or "?"


async def _reserve(ib: Any, contracts: list[Any]) -> int:
    """Wait until the lines this batch must open fit beside every other reader's; returns how many it took."""
    global _lines_open
    while True:
        need = sum(1 for c in contracts if _held_by_another(ib, c) is None)
        if need == 0 or _lines_open + need <= IBKR_BRIEF_LINE_BATCH:
            _lines_open += need
            return need
        await asyncio.sleep(IBKR_BRIEF_LINE_POLL_SEC)


async def _batch(ib: Any, contracts: list[Any], generic_ticks: str, prints: bool) -> dict[int, Any]:
    global _lines_open
    tickers: dict[int, Any] = {}
    opened: list[tuple[Any, Any, int]] = []   # (contract, ticker, listeners when this read opened it)
    reserved = await _reserve(ib, contracts)  # no await from here to the last reqMktData: held-ness cannot change
    try:
        for contract in contracts:
            held = _held_by_another(ib, contract)
            if held is not None:
                tickers[contract.conId] = held
                continue
            ticker = ib.reqMktData(contract, generic_ticks, False, False)
            _clear(ticker)   # no other line feeds it (checked above, with no await between): only this line's ticks
            tickers[contract.conId] = ticker
            opened.append((contract, ticker, _listeners(ticker)))
        await _settle(list(tickers.values()), prints)
    finally:
        for contract, ticker, before in opened:
            if _listeners(ticker) > before:
                logger.info("brief_lines: left %s's line open -- it gained a listener during the read", _name(contract))
                continue
            try:
                ib.cancelMktData(contract)
            except Exception:  # noqa: BLE001 -- a line that will not cancel is said, never raised into the read
                logger.warning("brief_lines: cancelling %s's line failed", _name(contract), exc_info=True)
        _lines_open = max(0, _lines_open - reserved)   # a line left open for a listener is the desk's now
    return tickers


async def read(ib: Any, contracts: list[Any], *, generic_ticks: str = "", prints: bool = False) -> dict[int, Any]:
    """``{conId: ticker}`` for every contract, ``IBKR_BRIEF_LINE_BATCH`` lines at a time.

    ``prints``: a ticker counts as priced only with a last trade (stocks). A ticker may hold no price: IBKR sent
    none before ``IBKR_BRIEF_LINE_WAIT_SEC``. Read its fields at once -- a cancelled line's ticker is not updated
    again, and a borrowed one keeps moving. Raises ``NoHeadroom`` before opening anything when a line must be
    opened and too few are spare; contracts the desk already streams need none.
    """
    if any(_held_by_another(ib, c) is None for c in contracts):
        guard()
    out: dict[int, Any] = {}
    async with timed("ibkr.brief_lines"):
        for i in range(0, len(contracts), IBKR_BRIEF_LINE_BATCH):
            out.update(await _batch(ib, contracts[i:i + IBKR_BRIEF_LINE_BATCH], generic_ticks, prints))
    return out


# -- stocks ------------------------------------------------------------------------------------------------------
async def stock_contracts(ib: Any, symbols: list[str], *,
                          timeout: float = IBKR_DISCOVERY_QUALIFY_TIMEOUT_SEC) -> dict[str, Any]:
    """``{SYM: qualified Stock}``, from Nova's qualified-contract cache first."""
    from ib_async import Stock

    from ibkr.qualified_contracts import remember_qualified_contract, take_qualified_contract

    have = {sym: take_qualified_contract(sym) for sym in symbols}
    missing = [sym for sym, c in have.items() if c is None]
    if missing:
        got = await asyncio.wait_for(ib.qualifyContractsAsync(*[Stock(sym, "SMART", "USD") for sym in missing]),
                                     timeout=timeout)
        for c in got or []:
            sym = str(getattr(c, "symbol", "") or "").upper() if c is not None else ""
            if sym and getattr(c, "conId", 0):
                remember_qualified_contract(sym, c)
                have[sym] = c
    return {sym: c for sym, c in have.items() if c is not None}


async def stock_quotes(symbols: list[str], *,
                       qualify_timeout: float = IBKR_DISCOVERY_QUALIFY_TIMEOUT_SEC) -> dict[str, dict]:
    """``{SYM: quote}`` in ``discovery.snapshot_quotes``' shape (``quote_rows.quote_from_ticker``), from brief lines.

    With no print by the deadline the price is IBKR's prior close, flagged ``close_fallback``; a symbol with
    neither is left out. Raises ``NoHeadroom`` (above); ``{}`` when IBKR is not connected.
    """
    from ibkr.loop_supervisor import is_ib_loop, is_started, on_ib

    if is_started() and not is_ib_loop():
        return await on_ib(stock_quotes(symbols, qualify_timeout=qualify_timeout),
                           qualify_timeout + IBKR_BRIEF_LINE_WAIT_SEC * (1 + len(symbols) // IBKR_BRIEF_LINE_BATCH)
                           + 5.0, label="brief_lines")
    from ibkr import client
    from ibkr.quote_rows import quote_from_ticker

    wanted = [str(s).strip().upper() for s in symbols if str(s or "").strip()]
    ib = client.get_ib()
    if not wanted or ib is None:
        return {}
    by_sym = await stock_contracts(ib, wanted, timeout=qualify_timeout)
    tickers = await read(ib, list(by_sym.values()), generic_ticks=IBKR_L1_GENERIC_TICKS, prints=True)
    out: dict[str, dict] = {}
    for sym, contract in by_sym.items():
        ticker = tickers.get(contract.conId)
        quote = quote_from_ticker(ticker) if ticker is not None else None
        if quote is not None:
            out[sym] = quote
    return out
