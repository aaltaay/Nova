"""Cold IBKR snapshot quote batching and mover row projections.

Split from ``ibkr/discovery.py`` along the two-step scanner pipeline seam:
  1. ``ibkr/discovery.py`` owns one-shot ``reqScannerSubscription`` discovery
     and Error 322 scanner-slot recovery.
  2. This module owns ``reqTickersAsync`` cold snapshot hydration (including
     budgeted chunking, qualified-contract reuse, and ``"snapshot"`` ticker
     reqId cleanup) plus the mover row projections built on top of it.
"""
from __future__ import annotations

import asyncio
import logging

from constants import (
    IBKR_COLD_SNAPSHOT_BATCH,
    IBKR_QUOTE_BATCH_TIMEOUT_SEC,
     IBKR_SCAN_CODE_AH_GAINERS,
    IBKR_SCAN_CODE_GAINERS,
    IBKR_SCAN_CODE_LOSERS,
    SCANNER_MIN_PRICE,
)
from ibkr import quote_rows as _quote_rows
from ibkr.errors import IbkrDiscoveryError, describe_exc
from ibkr.qualified_contracts import (
    remember_qualified_contract,
    take_qualified_contract,
)
from metrics.op_metrics import timed

logger = logging.getLogger(__name__)


def _cancel_snapshot_tickers(ib, contracts: list) -> None:
    """Cancel any still-open snapshot reqMktData lines after a snapshot batch.

    reqTickersAsync registers each ticker under tickType ``"snapshot"``
    (``startTicker(reqId, contract, "snapshot")``), so ``ib.cancelMktData``
    -- which looks up ``endTicker(ticker, "mktData")`` -- finds reqId 0 and
    reports "No reqId found". The correct cancel is to pop the reqId from the
    ``"snapshot"`` map and send ``client.cancelMktData(reqId)`` ourselves.

    Never raises; a contract with no live snapshot line is a no-op.
    """
    wrapper = getattr(ib, "wrapper", None)
    client = getattr(ib, "client", None)
    if wrapper is None or client is None:
        return
    tickers_by_hash = getattr(wrapper, "tickers", None) or {}
    t2r = getattr(wrapper, "ticker2ReqId", None) or {}
    snap_map = t2r.get("snapshot") or {}
    for contract in contracts:
        try:
            ticker = tickers_by_hash.get(hash(contract))
            if ticker is None:
                continue
            req_id = snap_map.pop(ticker, 0) or 0
            if req_id:
                getattr(wrapper, "_reqId2Contract", {}).pop(req_id, None)
                client.cancelMktData(req_id)
        except Exception:
            logger.debug(
                "IBKR: snapshot cancel failed for %s",
                getattr(contract, "symbol", "?"),
                exc_info=True,
            )


def _log_budget_spent(budget_sec: float | None, answered: int, asked: int) -> None:
    logger.info(
        "IBKR: snapshot budget %.0fs spent -- %d of %d symbol(s) answered; the rest wait for the next call",
        float(budget_sec or 0.0), answered, asked,
    )


async def snapshot_quotes(
    symbols: list[str],
    *,
    timeout_sec: float = IBKR_QUOTE_BATCH_TIMEOUT_SEC,
    require_success: bool = False,
    budget_sec: float | None = None,
) -> dict[str, dict]:
    """Qualify + snapshot each symbol. Returns {symbol: {price, prev_close, open, volume}}.

    Reuses qualified contracts across ticks so the 1Hz table reprice loop does not
    pay qualifyContractsAsync on every second for the same universe.
    ``timeout_sec`` bounds a hung reqTickersAsync so table chunks stay responsive --
    each chunk of IBKR_COLD_SNAPSHOT_BATCH, not the call.

    ``budget_sec`` bounds the whole call: the qualify and each chunk wait at most
    what is left, no chunk starts after it, and what answered by then is returned
    (said in the log). Off hours IBKR takes up to ~11 s a chunk, so HOD Momo's
    40-symbol snapshot ran past the 25 s thread bridge every time and its answers
    were thrown away with the cancelled call (#891).

    When ``require_success`` is True (discovery/movers paths), disconnect /
    timeout / API failure raises ``IbkrDiscoveryError`` instead of returning ``{}``
    (which callers previously treated as a successful empty market).
    """
    from ibkr import discovery as _discovery
    from ibkr.loop_supervisor import is_ib_loop, is_started, on_ib

    if is_started() and not is_ib_loop():
        return await on_ib(
            snapshot_quotes(
                symbols, timeout_sec=timeout_sec, require_success=require_success,
                budget_sec=budget_sec,
            ),
            max(1.0, float(timeout_sec if budget_sec is None else budget_sec) + 5.0),
            label="snapshot_quotes",
        )
    if not symbols:
        return {}

    ib = _discovery._client.get_ib()
    if ib is None or not _discovery._load_ib_types():
        if require_success:
            raise IbkrDiscoveryError("IBKR not connected for snapshot quotes")
        return {}

    symbols = [s.upper() for s in symbols]
    clock = asyncio.get_running_loop()
    budget_end = None if budget_sec is None else clock.time() + max(0.5, float(budget_sec))

    def _wait(cap: float) -> float:
        """``cap``, or what is left of the budget when that is less (never under half a second)."""
        if budget_end is None:
            return max(0.5, float(cap))
        return max(0.5, min(float(cap), budget_end - clock.time()))

    qualify_timeout = _discovery.IBKR_DISCOVERY_QUALIFY_TIMEOUT_SEC
    missing = [s for s in symbols if s not in _discovery._qualified_contracts]
    if missing:
        contracts = [_discovery._Stock(sym, "SMART", "USD") for sym in missing]
        try:
            qualified = await asyncio.wait_for(
                ib.qualifyContractsAsync(*contracts),
                timeout=_wait(qualify_timeout),
            )
        except asyncio.TimeoutError as exc:
            detail = f"qualify batch timed out after {qualify_timeout:.0f}s"
            logger.warning("IBKR: %s (%d symbols)", detail, len(contracts))
            if require_success:
                raise IbkrDiscoveryError(detail) from exc
            qualified = []
        except Exception as exc:
            detail = describe_exc(exc)
            logger.exception("IBKR: qualify batch failed: %s", detail)
            if require_success:
                raise IbkrDiscoveryError(f"qualify failed: {detail}") from exc
            qualified = []
        for c in qualified:
            if c is None:
                continue
            sym = getattr(c, "symbol", None)
            if sym:
                remember_qualified_contract(sym.upper(), c)

    qualified = [c for s in symbols if (c := take_qualified_contract(s)) is not None]
    if not qualified:
        if require_success:
            raise IbkrDiscoveryError(
                f"no qualified contracts for {len(symbols)} snapshot symbol(s)"
            )
        return {}

    from ibkr.ib_scheduler import ColdDropped, cold_slot

    tickers: list = []
    batch_n = max(1, int(IBKR_COLD_SNAPSHOT_BATCH))
    try:
        async with timed("ibkr.snapshot_quotes"):
            for i in range(0, len(qualified), batch_n):
                if budget_end is not None and clock.time() >= budget_end:
                    _log_budget_spent(budget_sec, len(tickers), len(qualified))
                    break
                chunk = qualified[i : i + batch_n]
                try:
                    async with cold_slot(label="snapshot_quotes", droppable=True):
                        try:
                            got = await asyncio.wait_for(
                                ib.reqTickersAsync(*chunk),
                                timeout=_wait(timeout_sec),
                            )
                            if got:
                                tickers.extend(got)
                        finally:
                            _cancel_snapshot_tickers(ib, chunk)
                except ColdDropped:
                    logger.info(
                        "IBKR: snapshot_quotes dropped (%d remaining) -- interactive preempt",
                        len(qualified) - i,
                    )
                    break
                except asyncio.TimeoutError:
                    if budget_end is None:
                        raise
                    # A budgeted call keeps what answered; the chunk that ran out is asked next time.
                    _log_budget_spent(budget_sec, len(tickers), len(qualified))
                    break
    except asyncio.TimeoutError as exc:
        logger.warning(
            "IBKR: snapshot timeout (%.1fs) for %d symbols",
            timeout_sec, len(qualified),
        )
        if require_success:
            raise IbkrDiscoveryError(
                f"snapshot timeout ({timeout_sec:.1f}s) for {len(qualified)} symbols"
            ) from exc
        return {}
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        detail = describe_exc(exc)
        logger.exception("IBKR: snapshot batch failed: %s", detail)
        if require_success:
            raise IbkrDiscoveryError(f"snapshot failed: {detail}") from exc
        return {}

    out: dict[str, dict] = {}
    for t in tickers:
        sym = getattr(t.contract, "symbol", None)
        quote = _quote_rows.quote_from_ticker(t) if sym else None
        if quote is not None:
            out[sym] = quote
    return out


def chunk_symbols(symbols: list[str], chunk_size: int) -> list[list[str]]:
    """Split symbols into fixed-size batches for progressive table reprice."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    ordered = [s for s in symbols if s]
    return [ordered[i : i + chunk_size] for i in range(0, len(ordered), chunk_size)]


async def _get_movers(
    scan_code: str, reverse: bool, *, below_price: float | None = None,
) -> list[dict]:
    from ibkr import discovery as _discovery

    symbols = await _discovery.scan_symbols(scan_code, below_price=below_price)
    if not symbols:
        return []
    quotes = await _discovery.snapshot_quotes(symbols, require_success=True)

    rows = [
        _quote_rows.mover_row_from_quote(sym, q)
        for sym, q in quotes.items()
        if q["price"] >= SCANNER_MIN_PRICE and q["prev_close"]
    ]
    rows.sort(key=lambda x: x["change_pct"], reverse=reverse)
    return rows


async def get_gainers() -> list[dict]:
    """Top % gainers, intraday (current price vs prior close)."""
    return await _get_movers(IBKR_SCAN_CODE_GAINERS, reverse=True)


async def get_losers() -> list[dict]:
    """Top % losers, intraday (current price vs prior close)."""
    return await _get_movers(IBKR_SCAN_CODE_LOSERS, reverse=False)


async def get_afterhours_gainers() -> list[dict]:
    """Dedicated after-hours movers scan (TOP_AFTER_HOURS_PERC_GAIN).

    Distinct IB scan universe from TOP_PERC_GAIN -- the After Hours tab's
    primary source. Reshaping ``get_gainers()``'s intraday result is a
    fallback only, used when this scan is empty.
    """
    return await _get_movers(IBKR_SCAN_CODE_AH_GAINERS, reverse=True)
