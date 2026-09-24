"""
IBKR tick-by-tick Time & Sales stream.

Uses reqTickByTickData("AllLast") — every print as it appears in the TWS
Time & Sales window. One stream per open symbol, refcounted like depth.py.

IB limitation: no second reqTickByTickData for the same instrument within
15 seconds. The 15s debounce tracks when we last cancelled a subscription
and refuses to resubscribe until the window clears.

How a line ends, and saying so, is ``ibkr/tape_line.py`` (#525).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from constants import IBKR_TAPE_TICK_TYPE
from ibkr import client as _client
from ibkr import depth as _depth
from ibkr import tape_line as _tape_line
from ibkr.tape_events import warm_10sec_fill as _warm_10sec_fill
from metrics.op_metrics import timed_sync
from perf.counters import incr as _count_drop

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
            _count_drop("tape.viewer_dropped")
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except asyncio.QueueEmpty:
                logger.debug("IBKR tape: queue empty after full for %s", symbol)
            except asyncio.QueueFull:
                logger.warning("IBKR tape: queue still full for %s after drop", symbol)


def _on_tape_update(ticker: Any, symbol: str) -> None:
    from ibkr.tape_events import on_tape_update
    on_tape_update(ticker, symbol, _push_queue, _depth)


# Maps an IB error to the line it ended, by request id (#525).
_on_ib_error = _tape_line.on_ib_error


def _install_error_hook(ib: Any) -> None:
    if id(ib) in _error_hooked_ib_ids:
        return
    ib.errorEvent += _on_ib_error
    _error_hooked_ib_ids.add(id(ib))


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
    _tape_line.reset_for_tests()


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
    wait_remaining = guard_remaining(symbol)
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
        from ibkr.tape_recording import subscribed
        subscribed(symbol)
        req_id = _tape_line.note_subscribed(symbol, ib, contract)
        logger.info("IBKR tape: subscribed %s (AllLast, reqId %s)", symbol, req_id)
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
    if not _drop_line(symbol, "no viewer left"):
        return
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


def end_line(symbol: str, why: str, *, notify: bool = True) -> bool:
    """The line is dead (#525): IBKR ended it, or a recording found it silent.

    Cancel it so the next request is a real one -- ib_async hands back a line it
    still has registered. Viewers keep their queues and references, so a new line
    feeds them; ``notify`` shows them ``why`` (IBKR's error). The IB 15 s guard
    applies from now. False when there was no line to drop.
    """
    symbol = symbol.upper()
    had = _drop_line(symbol, why)
    if notify:
        from ibkr.tape_recording import rejected
        rejected(symbol, why)
        _push_queue(symbol, {"type": "error", "symbol": symbol, "message": why})
    return had


def guard_remaining(symbol: str, now: float | None = None) -> float:
    """Seconds before IB takes another request for this symbol's tape (0 when free)."""
    last = _cancelled_at.get(symbol.upper(), 0.0)
    return max(0.0, IBKR_TAPE_RESUBSCRIBE_GUARD_SEC - ((time.time() if now is None else now) - last))


def _drop_line(symbol: str, why: str) -> bool:
    """Cancel the IB line and forget it; False when there was none."""
    _cancel_linger(symbol)
    sub = _tickers.pop(symbol, None)
    contract = _contracts.pop(symbol, None)
    if sub is None:
        return False
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
    _tape_line.note_dropped(symbol, why)
    return True


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
    except ValueError:  # maintainer: allow-swallow closing an already-closed viewer queue is a no-op
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
