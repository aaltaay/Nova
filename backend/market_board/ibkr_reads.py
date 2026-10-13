"""The Market page's IBKR reads (ADR 053), run from its refresher threads on the IB loop (``run_coro``).

- ``reference_quotes``: snapshots of the tiles' futures / indexes / crypto and NYSE's indicators, a few at a time
  in the cold, droppable slot; each carries IBKR's market-data type and, when refused, IBKR's own error.
- ``stock_quotes``: ETFs and stocks through the existing cold ``snapshot_quotes`` path.
- ``line_bars`` / ``rth_closes``: paced historical requests at background priority.
- ``movers``: IBKR's large-cap gainers scan, one shot, always cancelled.
- ``industries``: each symbol's IBKR industry / category / subcategory (contract details).

None of these holds a streaming line: every IBKR read refuses (``NoHeadroom``) while fewer than
``MARKET_MIN_FREE_LINES`` of the account's market-data lines are free, and none places anything.
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any

from constants_market_board import (
    MARKET_CLOSES_DURATION,
    MARKET_HISTORY_TIMEOUT_SEC,
    MARKET_IBKR_TIMEOUT_SEC,
    MARKET_INDUSTRY_GAP_SEC,
    MARKET_LINE_BAR,
    MARKET_LINE_DURATION,
    MARKET_MIN_FREE_LINES,
    MARKET_MOVERS_ROWS,
    MARKET_MOVERS_SCAN,
    MARKET_SNAPSHOT_BATCH,
)
from market_board import contracts
from market_board.state import Stated

SOURCE = "ibkr"
DATA_TYPES = {1: "live", 2: "frozen", 3: "delayed", 4: "delayed_frozen"}


class NoHeadroom(Exception):
    """Too few market-data lines are free: the page waits rather than compete with the desk."""


class SourceError(Stated):
    """IBKR answered, but not with what the read needs (stated on the page as the reason)."""


def ready() -> bool:
    from ibkr import client

    return client.is_ready()


def free_lines() -> int | None:
    try:
        from ibkr import ticks

        return int(ticks.ticker_budget_status()["reqMktData_remaining"])
    except Exception:  # noqa: BLE001 -- unknown budget: the guard below lets the read run as the desk's own reads do
        return None


def _guard() -> None:
    free = free_lines()
    if free is not None and free < MARKET_MIN_FREE_LINES:
        raise NoHeadroom(f"only {free} market-data lines free (the page waits for {MARKET_MIN_FREE_LINES})")


def _run(coro, timeout: float, label: str):
    from ibkr.client_bridge import run_coro

    return run_coro(coro, timeout, label=label)


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _quote(ticker: Any, spec: dict, contract: Any, error: str | None) -> dict:
    last = _num(getattr(ticker, "last", None))
    bid, ask = _num(getattr(ticker, "bid", None)), _num(getattr(ticker, "ask", None))
    basis = "last"
    if last is None and spec.get("sec_type") == "CRYPTO" and bid and ask and bid > 0 and ask > 0:
        last, basis = (bid + ask) / 2.0, "mid"   # a coin with no print in the snapshot: the quoted midpoint
    return {
        "id": spec["id"], "last": last, "price_basis": basis if last is not None else None,
        "prev_close": _num(getattr(ticker, "close", None)),
        "bid": bid, "ask": ask,
        "bid_size": _num(getattr(ticker, "bidSize", None)), "ask_size": _num(getattr(ticker, "askSize", None)),
        "data_type": DATA_TYPES.get(int(getattr(ticker, "marketDataType", 0) or 0)),
        "contract": contracts.local_symbol(contract), "at": time.time(), "error": error,
    }


def reference_quotes(specs: list[dict], trading_date: str) -> dict[str, dict]:
    """``{spec id: quote}`` for every spec IBKR resolved; a refused one carries ``error`` and no numbers."""
    _guard()

    async def _ask() -> dict[str, dict]:
        from ibkr import client, reference_errors
        from ibkr.discovery import _cancel_snapshot_tickers
        from ibkr.ib_scheduler import ColdDropped, cold_slot

        ib = client.get_ib()
        if ib is None:
            raise SourceError("IBKR is not connected")
        out: dict[str, dict] = {}
        pairs: list[tuple[dict, Any]] = []
        for spec in specs:
            started = time.time()
            contract = await contracts.resolve(ib, spec, trading_date)
            if contract is None:
                why = reference_errors.describe(reference_errors.last_error(
                    sec_type=spec["sec_type"], symbol=spec["symbol"], since=started - 1))
                out[spec["id"]] = _quote(None, spec, None, why or "IBKR does not know this contract")
                continue
            pairs.append((spec, contract))
        for i in range(0, len(pairs), MARKET_SNAPSHOT_BATCH):
            chunk = pairs[i:i + MARKET_SNAPSHOT_BATCH]
            batch = [c for _, c in chunk]
            started = time.time()
            silent = None
            tickers: list = []
            try:
                async with cold_slot(label="market_board.quotes", droppable=True):
                    try:
                        tickers = await asyncio.wait_for(ib.reqTickersAsync(*batch), timeout=MARKET_IBKR_TIMEOUT_SEC)
                    except asyncio.TimeoutError:  # maintainer: allow-swallow the tiles say IBKR sent nothing
                        silent = f"IBKR sent nothing within {MARKET_IBKR_TIMEOUT_SEC:.0f} s"
                    finally:
                        _cancel_snapshot_tickers(ib, batch)
            except ColdDropped:
                break   # interactive work has the slot; the next turn asks again
            by_id = {getattr(t.contract, "conId", 0): t for t in tickers or []}
            for spec, contract in chunk:
                err = reference_errors.describe(reference_errors.last_error(con_id=contract.conId, since=started - 1))
                out[spec["id"]] = _quote(by_id.get(contract.conId), spec, contract, err or silent)
        return out

    budget = MARKET_IBKR_TIMEOUT_SEC * (2 + len(specs)) + 10
    return _run(_ask(), budget, "market_board.reference_quotes") or {}


def stock_quotes(symbols: list[str]) -> dict[str, dict]:
    """``{SYM: {price, prev_close, no_trade}}`` from IBKR's cold snapshots of ETFs and stocks."""
    if not symbols:
        return {}
    _guard()
    from constants import IBKR_QUOTE_BATCH_TIMEOUT_SEC, IBKR_QUOTE_QUALITY_CLOSE_FALLBACK
    from ibkr.discovery import snapshot_quotes

    got = _run(snapshot_quotes(list(symbols)), IBKR_QUOTE_BATCH_TIMEOUT_SEC * 2 + 10, "market_board.stock_quotes") or {}
    out: dict[str, dict] = {}
    for sym, q in got.items():
        if not isinstance(q, dict):
            continue
        no_trade = q.get("quote_quality") == IBKR_QUOTE_QUALITY_CLOSE_FALLBACK
        out[str(sym).upper()] = {"price": None if no_trade else _num(q.get("price")),
                                 "prev_close": _num(q.get("prev_close")), "no_trade": no_trade}
    return out


def line_bars(spec: dict, trading_date: str) -> list[list[float]]:
    """``[[t, close]]`` of today's 5-minute bars for a tile (oldest first, all hours)."""
    from ibkr import historical_service

    async def _ask() -> list[dict]:
        from ibkr import client

        ib = client.get_ib()
        if ib is None:
            raise SourceError("IBKR is not connected")
        contract = await contracts.resolve(ib, spec, trading_date)
        if contract is None:
            raise SourceError("IBKR does not know this contract")
        what = "AGGTRADES" if spec["sec_type"] == "CRYPTO" else "TRADES"
        return await historical_service.request_reference_bars(
            f"{spec['sec_type']}:{spec['symbol']}", contract, duration=MARKET_LINE_DURATION,
            bar_size=MARKET_LINE_BAR, what_to_show=what, use_rth=False)

    rows = _run(_ask(), MARKET_HISTORY_TIMEOUT_SEC * 2, "market_board.line_bars") or []
    return [[row["t"], row["close"]] for row in rows]


def rth_closes(symbol: str) -> list[list]:
    """``[[session date, regular-hours close]]`` oldest first; ``HistoricalShed`` when IBKR's budget says later."""
    from ibkr import historical_service

    rows = _run(historical_service.request_rth_daily_closes(symbol, MARKET_CLOSES_DURATION),
                MARKET_HISTORY_TIMEOUT_SEC * 2, "market_board.rth_closes")
    return [[day, close] for day, close in rows or []]


def movers() -> list[str]:
    """IBKR's large-cap gainers scan (``MARKET_MOVERS_SCAN``), ranked symbols; the subscription is always cancelled."""
    _guard()

    async def _ask() -> list[str]:
        from ib_async import ScannerSubscription

        from constants import IBKR_SCAN_INSTRUMENT, IBKR_SCAN_LOCATION
        from ibkr import client, discovery

        ib = client.get_ib()
        if ib is None:
            raise SourceError("IBKR is not connected")
        sub = ScannerSubscription(numberOfRows=MARKET_MOVERS_ROWS, instrument=IBKR_SCAN_INSTRUMENT,
                                  locationCode=IBKR_SCAN_LOCATION, **dict(MARKET_MOVERS_SCAN))
        async with discovery._get_scan_lock():   # one scan at a time with the desk's own one-shot scans
            rows = await discovery._one_shot_scanner(ib, sub)
        out: list[str] = []
        for row in rows:
            sym = getattr(getattr(getattr(row, "contractDetails", None), "contract", None), "symbol", None)
            if sym and sym.upper() not in out:
                out.append(sym.upper())
        return out

    return _run(_ask(), MARKET_IBKR_TIMEOUT_SEC * 3, "market_board.movers") or []


def industries(symbols: list[str]) -> dict[str, dict]:
    """``{SYM: {industry, category, subcategory}}`` from IBKR's contract details; an empty answer is all ``None``."""
    if not symbols:
        return {}

    async def _ask() -> dict[str, dict]:
        from ib_async import Stock

        from ibkr import client

        ib = client.get_ib()
        if ib is None:
            raise SourceError("IBKR is not connected")
        out: dict[str, dict] = {}
        for sym in symbols:
            details = await asyncio.wait_for(ib.reqContractDetailsAsync(Stock(sym, "SMART", "USD")),
                                             timeout=MARKET_IBKR_TIMEOUT_SEC)
            first = details[0] if details else None
            out[sym] = {k: (getattr(first, k, None) or None) for k in ("industry", "category", "subcategory")}
            await asyncio.sleep(MARKET_INDUSTRY_GAP_SEC)
        return out

    budget = (MARKET_IBKR_TIMEOUT_SEC + MARKET_INDUSTRY_GAP_SEC) * len(symbols) + 10
    return _run(_ask(), budget, "market_board.industries") or {}
