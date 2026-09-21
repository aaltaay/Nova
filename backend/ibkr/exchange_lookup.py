"""Cold, paced per-symbol listing-exchange lookup for scanner rows (issue #90).

IB scan rows rarely carry ``contract.primaryExchange``, so ``row["exchange"]``
is blank for most names and the Exchange column reads as "unknown". This module
buys that field with ONE qualified-contract round trip per NEW symbol, modelled
on ``ibkr/listing_flags.py``: the same ``qualifyContractsAsync`` call, bounded
by the same ``IBKR_L1_QUALIFY_TIMEOUT_SEC``, marshalled onto the IB loop through
``loop_supervisor.on_ib``. No second, unpaced request path is opened.

Three rules make it safe to run against a live premarket roster:

* **Never awaited on admit.** ``note_rows`` only records symbols and, at most,
  creates a background task. ADR 010 name-only admission is untouched, so a
  slow or dead Gateway can never delay a row appearing or its first L1 tick.
* **Once per symbol per session.** A symbol enters ``_resolved`` as soon as a
  round trip has been *attempted* -- success, IB-side error or timeout alike --
  so a refresh, a re-rank or a per-tick patch can never buy a second one. One
  round trip per new symbol is the budget the operator approved; spending a
  second on a retry is not. A symbol is only re-queued when no round trip
  happened at all (Gateway not connected), which costs nothing.
* **Fail open.** Every answer routes through ``exchanges.normalize_ib_exchange``,
  which returns ``None`` for anything it does not recognise. An unknown, failed
  or slow lookup leaves the column blank -- exactly today's behaviour, with the
  UI filter treating the row as unfiltered. It never guesses a value.

Results are read back through ``cached_exchange`` by ``ibkr/scanner_hydrate.py``,
which backfills ``row["exchange"]`` **only when it is empty** -- a
``primaryExchange`` the scan already supplied is never overwritten.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Iterable

from constants import (
    IBKR_EXCHANGE_LOOKUP_MAX_PENDING,
    IBKR_EXCHANGE_LOOKUP_PACE_SEC,
    IBKR_L1_QUALIFY_TIMEOUT_SEC,
)
from ibkr import client as _client

logger = logging.getLogger(__name__)

# symbol -> normalized exchange, or None when IB gave no usable answer.
# Presence is the "already spent a round trip" ledger, so None is a real entry.
_resolved: dict[str, str | None] = {}
_pending: deque[str] = deque()
_queued: set[str] = set()
_worker: asyncio.Task | None = None


def cached_exchange(symbol: str) -> str | None:
    """Normalized exchange for *symbol*, or None when unknown/not looked up."""
    if not symbol:
        return None
    return _resolved.get(symbol.strip().upper())


def pending_count() -> int:
    """Symbols queued for a lookup (diagnostics + tests)."""
    return len(_pending)


def resolved_count() -> int:
    """Symbols whose one round trip has been spent (diagnostics + tests)."""
    return len(_resolved)


def reset_for_tests() -> None:
    global _worker
    _resolved.clear()
    _pending.clear()
    _queued.clear()
    _worker = None


def note_rows(rows: Iterable[dict]) -> None:
    """Queue a lookup for every row whose exchange is still empty.

    Returns immediately -- this is called from the roster hydrate path and must
    never make admission wait on IB.
    """
    note_symbols(
        (row.get("symbol") or "")
        for row in rows
        if not row.get("exchange")
    )


def note_symbols(symbols: Iterable[str]) -> None:
    """Queue *symbols* for a paced lookup, skipping ones already spent."""
    added = 0
    capped = False
    for raw in symbols:
        sym = (raw or "").strip().upper()
        if not sym or sym in _resolved or sym in _queued:
            continue
        if len(_queued) >= IBKR_EXCHANGE_LOOKUP_MAX_PENDING:
            capped = True
            break
        _queued.add(sym)
        _pending.append(sym)
        added += 1
    if capped:
        logger.warning(
            "exchange_lookup: queue at cap (%d) -- remaining symbols wait for a later commit",
            IBKR_EXCHANGE_LOOKUP_MAX_PENDING,
        )
    if added:
        _ensure_worker()


def _ensure_worker() -> None:
    """Start the single drain task if one is not already running."""
    global _worker
    if _worker is not None and not _worker.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop (tests, sync callers): symbols stay queued for the next call
        # that does have one. Never block the caller to make up for it.
        logger.debug(
            "exchange_lookup: no running loop -- %d symbol(s) stay queued",
            len(_pending),
        )
        return
    _worker = loop.create_task(drain_pending(), name="ibkr.exchange_lookup")


async def drain_pending() -> None:
    """Resolve queued symbols one at a time, paced. Started by ``note_symbols``."""
    global _worker
    import exchanges as _exchanges

    try:
        while _pending:
            ib = _client.get_ib()
            if ib is None or not ib.isConnected():
                # No round trip happened, so nothing is spent: drop the queue
                # and let the next roster commit re-offer these symbols.
                logger.debug(
                    "exchange_lookup: Gateway not connected -- re-queueing %d symbol(s) later",
                    len(_pending),
                )
                _pending.clear()
                _queued.clear()
                return
            sym = _pending.popleft()
            _queued.discard(sym)
            exch = await _lookup(ib, sym)
            _resolved[sym] = exch
            if exch:
                # Publish so REST/WS serialization (exchanges.attach_exchanges)
                # fills the row on the next response, not the next roster batch.
                _exchanges.remember_ib_exchange(sym, exch)
            if _pending:
                await asyncio.sleep(float(IBKR_EXCHANGE_LOOKUP_PACE_SEC))
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("exchange_lookup: drain failed -- queue left for a later commit")
    finally:
        _worker = None


async def _lookup(ib, symbol: str) -> str | None:
    """One qualify round trip. Returns a normalized exchange, or None."""
    import exchanges as _exchanges
    from ib_async import Stock

    from ibkr.loop_supervisor import is_ib_loop, is_started, on_ib

    timeout = float(IBKR_L1_QUALIFY_TIMEOUT_SEC)
    coro = ib.qualifyContractsAsync(Stock(symbol, "SMART", "USD"))
    try:
        if is_started() and not is_ib_loop():
            qualified = await on_ib(coro, timeout, label="exchange_lookup.qualify")
        else:
            qualified = await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Fail open: blank column, filter unfiltered. Same as today.
        logger.warning("exchange_lookup: qualify failed for %s: %s", symbol, exc)
        return None
    if not qualified:
        logger.debug("exchange_lookup: %s not qualified on IBKR", symbol)
        return None
    contract = qualified[0]
    return _exchanges.normalize_ib_exchange(
        getattr(contract, "primaryExchange", None) or getattr(contract, "exchange", None)
    )
