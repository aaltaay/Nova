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
# Fan-out: one queue per *viewer*, not one shared queue per symbol. Two
# viewers of the same symbol (StrictMode double-mount, or a genuine second
# Trader tab) must each see every print -- a single shared queue makes them
# competing consumers instead, so whichever socket's handler task keeps
# winning the race starves the other (see PROBLEM_LOG 2026-08-25: a live
# soak proved 1,902 archived DAIC prints delivered zero of them to the
# surviving viewer while a discarded StrictMode socket was still alive).
_viewer_queues: dict[str, list[asyncio.Queue]] = {}
_ws_viewers: dict[str, int] = {}
# Unix time when we last cancelled a symbol's tick-by-tick subscription.
_cancelled_at: dict[str, float] = {}
_linger_tasks: dict[str, asyncio.Task] = {}
_error_hooked_ib_ids: set[int] = set()
# Serializes subscribe_async per symbol so two concurrent viewers (e.g. a
# React StrictMode double-mount) cannot both build a queue / attach a
# handler for the same symbol (see PROBLEM_LOG 2026-08-25 tape freeze).
_subscribe_locks: dict[str, asyncio.Lock] = {}

IBKR_TAPE_RESUBSCRIBE_GUARD_SEC = 16.0  # IB requires 15s gap; add 1s margin
# Last WS viewer left -- keep the IB line up so Scanner/Trader remounts reuse it.
IBKR_TAPE_LINGER_SEC = 16.0
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


def _should_warm_10sec(symbol: str) -> bool:
    """Mirrors the store-settled guard ``routes/ticker.py`` uses for its warm
    timeframes -- true when the store is missing, incomplete, or stale."""
    import bars_store
    from constants import IBKR_10SEC_FETCH_BARS

    stored = bars_store.read(symbol, "10Sec", IBKR_10SEC_FETCH_BARS)
    if not stored or not stored.get("bars"):
        return True
    if not bars_store.store_series_complete("10Sec", len(stored["bars"])):
        return True
    return not bars_store.is_coverage_fresh(stored.get("coverage"), "10Sec")


def _warm_10sec_fill(symbol: str) -> None:
    """First Trader tape subscriber for a symbol warms its 10Sec hist fill
    (D-003) -- ``priority="warm"`` sheds on any pacing wait, so this never
    competes with a genuinely empty pane's ``open_chart`` fill."""
    try:
        if not _should_warm_10sec(symbol):
            return
        from constants import IBKR_10SEC_FETCH_BARS
        from ibkr.historical_service import schedule_fill

        schedule_fill(symbol, "10Sec", IBKR_10SEC_FETCH_BARS, priority="warm")
    except Exception:
        logger.debug("IBKR tape: 10Sec warm schedule failed for %s", symbol, exc_info=True)


def _clean(x: float | None) -> float | None:
    if x is None:
        return None
    try:
        return None if math.isnan(x) else float(x)
    except TypeError:
        return None


def _push_queue(symbol: str, payload: dict) -> None:
    """Broadcast payload to every viewer currently watching this symbol."""
    try:
        from sensors.rings import observe_print

        observe_print(symbol, payload)
    except Exception:
        logger.debug("IBKR tape: sensor ring skip for %s", symbol, exc_info=True)
    for q in list(_viewer_queues.get(symbol, ())):
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
        # P6 — durable local archive (non-fatal if archive package fails).
        # ADR 010: this runs inside the ib_async socket callback, so it must
        # only enqueue. A synchronous SQLite write here starved reqMktData for
        # the whole desk on high-print runners (2026-08-18 IB-loop wedge).
        try:
            from archive.capture import parse_iso_to_unix
            from archive.write_queue import enqueue_tape_print
            from constants import ARCHIVE_SOURCE_IBKR

            print_ts = parse_iso_to_unix(ts_iso)
            enqueue_tape_print(
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
                queued=True,
            )
            # Provisional 10Sec chart bars (D-003 / ADR 012) -- paints the
            # Trader 10Sec pane in seconds instead of waiting on the paced
            # 4h IB historical fill. Hist fill still lands and replaces.
            from ibkr import tape_10sec as _tape_10sec

            _tape_10sec.on_print(symbol, price, float(size_i), print_ts)
        except Exception:
            logger.exception("IBKR tape: archive enqueue failed for %s", symbol)

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


def reset_for_tests() -> None:
    """Drop in-memory tape state (unit tests only)."""
    for task in list(_linger_tasks.values()):
        if not task.done():
            task.cancel()
    _linger_tasks.clear()
    _contracts.clear()
    _tickers.clear()
    _viewer_queues.clear()
    _ws_viewers.clear()
    _cancelled_at.clear()
    _error_hooked_ib_ids.clear()
    _subscribe_locks.clear()


def prune_idle_maps(now: float | None = None) -> dict[str, int]:
    """Drop cancel/lock entries that are past the 15s resubscribe guard (D-024)."""
    stamp = now if now is not None else time.time()
    dropped_cancel = 0
    dropped_locks = 0
    for sym, cancelled in list(_cancelled_at.items()):
        if stamp - cancelled <= IBKR_TAPE_RESUBSCRIBE_GUARD_SEC:
            continue
        if sym in _tickers or _ws_viewers.get(sym, 0) > 0:
            continue
        _cancelled_at.pop(sym, None)
        dropped_cancel += 1
        lock = _subscribe_locks.get(sym)
        if lock is not None and not lock.locked():
            _subscribe_locks.pop(sym, None)
            dropped_locks += 1
    return {"cancelled_at": dropped_cancel, "subscribe_locks": dropped_locks}


def _cancel_linger(symbol: str) -> None:
    task = _linger_tasks.pop(symbol, None)
    if task is not None and not task.done():
        task.cancel()


def _schedule_linger(symbol: str) -> None:
    """Delay IB cancel so a remount can reuse the live tick-by-tick line."""
    _cancel_linger(symbol)

    async def _later() -> None:
        try:
            await asyncio.sleep(IBKR_TAPE_LINGER_SEC)
        except asyncio.CancelledError:
            return
        # A viewer may have reattached without going through subscribe_async
        # (is_subscribed() was already true, so ws_tape skipped straight to
        # streaming) -- release only if the line is still actually idle.
        # Without this re-check, a StrictMode double-mount schedules a
        # linger from the discarded socket's cleanup, and 16s later it
        # silently cancels a line the surviving socket is watching (see
        # PROBLEM_LOG 2026-08-25 -- DAIC/WVVIP tape freeze).
        if viewer_count(symbol) > 0:
            logger.info(
                "IBKR tape: linger expired for %s but viewer reattached -- keeping line",
                symbol,
            )
            _linger_tasks.pop(symbol, None)
            return
        _release_subscription(symbol)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _release_subscription(symbol)
        return
    _linger_tasks[symbol] = loop.create_task(_later())


async def subscribe_async(symbol: str) -> dict:
    """Subscribe to tick-by-tick AllLast for a symbol.

    Returns {"ok": True/False, "error": None/"..."}.
    Safe to call multiple times — idempotent once subscribed.
    """
    symbol = symbol.upper()
    _cancel_linger(symbol)
    ib = _client.get_ib()
    if ib is None:
        return {"ok": False, "error": _client.unavailable_detail("IBKR tape")}
    if not _load_ib_types():
        return {"ok": False, "error": "ib_async not available"}

    if symbol in _tickers:
        return {"ok": True, "error": None}

    # Serialize per symbol: two concurrent callers (StrictMode double-mount,
    # or a remount racing a slow qualifyContractsAsync) must not both build
    # a queue and attach a handler for the same symbol.
    prune_idle_maps()
    lock = _subscribe_locks.setdefault(symbol, asyncio.Lock())
    async with lock:
        return await _subscribe_locked(symbol, ib)


async def _subscribe_locked(symbol: str, ib: Any) -> dict:
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
        return {"ok": False, "error": str(exc)}

    _warm_10sec_fill(symbol)
    return {"ok": True, "error": None}


def unsubscribe(symbol: str) -> None:
    """Last WS viewer left. Linger before IB cancel so a remount can reuse."""
    symbol = symbol.upper()
    if symbol not in _tickers:
        return
    _schedule_linger(symbol)


def _release_subscription(symbol: str) -> None:
    symbol = symbol.upper()
    _cancel_linger(symbol)
    sub = _tickers.pop(symbol, None)
    contract = _contracts.pop(symbol, None)
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
    prune_idle_maps()
    logger.info("IBKR tape: unsubscribed %s", symbol)
    # Any viewer still watching (should not normally happen -- unsubscribe
    # only runs after the last viewer closed and the linger re-check found
    # nothing) gets told so its socket closes and reconnects instead of
    # sitting on a dead line behind a stale "LIVE" badge.
    _push_queue(
        symbol,
        {
            "type": "error",
            "symbol": symbol,
            "message": "Tape line dropped -- reconnecting",
            "released": True,
        },
    )


def ws_viewer_opened(symbol: str) -> None:
    # A reattaching viewer that finds is_subscribed() already true skips
    # subscribe_async entirely, so it must cancel a pending linger itself.
    _cancel_linger(symbol)
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


def is_subscribed(symbol: str) -> bool:
    """Is there an active IB tick-by-tick line for this symbol right now."""
    return symbol in _tickers


def open_viewer_queue(symbol: str) -> asyncio.Queue:
    """Register a new viewer's own queue so it gets every broadcast print.

    Each caller (each WS connection) must hold exactly one queue and pass
    it to ``stream()``; release it via ``close_viewer_queue`` in a
    ``finally`` block regardless of how the connection ends.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=IBKR_TAPE_QUEUE_MAXSIZE)
    _viewer_queues.setdefault(symbol, []).append(q)
    return q


def close_viewer_queue(symbol: str, q: asyncio.Queue) -> None:
    queues = _viewer_queues.get(symbol)
    if not queues:
        return
    try:
        queues.remove(q)
    except ValueError:
        pass
    if not queues:
        _viewer_queues.pop(symbol, None)


async def stream(queue: asyncio.Queue):
    """AsyncGenerator yielding print dicts (or None on heartbeat timeout)
    for one viewer's own queue -- see ``open_viewer_queue``.
    """
    while True:
        try:
            print_data = await asyncio.wait_for(queue.get(), timeout=TAPE_STREAM_HEARTBEAT_SEC)
            yield print_data
        except asyncio.TimeoutError:
            yield None
