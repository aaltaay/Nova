"""The seat acts on each print and book, not on the next tick (ADR 068 decision 15).

The IBKR AllLast and depth callbacks call ``print_in`` / ``book_in`` for every print and book (ADR 010: they only
note and enqueue, never wait). For a stock the seat watches -- its stock, a break's, one Claude holds shares in --
the print is kept in a short ring and the watcher is woken at once, so a break's trigger and the guard are judged on
that print within ``AGENT_WAKE_MIN_SEC`` instead of up to ``AGENT_TICK_SEC`` later, and without waiting for the tape
archive's writer (the AIOK break, 2026-10-27, filled 13.20 against a 13.17 trigger).

Owner: the watched set, the rings (newest ``AGENT_WAKE_RING_SEC`` of each watched stock's prints, with bid / ask)
and the wake signal; all in memory, gone on a restart (the archive still answers then).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from typing import Any

from agent_trader.constants_agent_trader import AGENT_WAKE_RING_SEC

logger = logging.getLogger(__name__)

_PRINT_KEYS = ("ts", "price", "size", "bid", "ask", "exchange", "conditions", "unreported", "sets_price")
_lock = threading.Lock()
_watched: frozenset[str] = frozenset()
_rings: dict[str, deque[dict[str, Any]]] = {}
_since: dict[str, float] = {}          # symbol -> the ring holds every print after this (watching began, or trimmed)
_event: asyncio.Event | None = None
_loop: asyncio.AbstractEventLoop | None = None


def reset_for_tests() -> None:
    global _watched, _event, _loop
    with _lock:
        _watched = frozenset()
        _rings.clear()
        _since.clear()
    _event, _loop = None, None


def bind(loop: asyncio.AbstractEventLoop) -> asyncio.Event:
    """The watcher's loop and the event it waits on."""
    global _event, _loop
    _loop, _event = loop, asyncio.Event()
    return _event


def watch(symbols: set[str], now: float | None = None) -> None:
    """The stocks whose prints and books wake the seat now; a stock left out drops its ring."""
    global _watched
    t = time.time() if now is None else now
    wanted = frozenset(s.upper() for s in symbols if s)
    with _lock:
        for sym in wanted - _watched:
            _rings[sym] = deque()
            _since[sym] = t
        _watched = wanted
        for sym in [s for s in _rings if s not in wanted]:
            _rings.pop(sym, None)
            _since.pop(sym, None)


def _wake() -> None:
    loop, event = _loop, _event
    if loop is None or event is None:
        return
    try:
        loop.call_soon_threadsafe(event.set)
    except RuntimeError:
        pass  # maintainer: allow-swallow a closed loop at shutdown has no watcher left to wake


def print_in(payload: Any) -> None:
    """One live print (the AllLast handler's payload). Called on the IB loop: notes and wakes, never waits."""
    sym = str(payload.get("symbol") or "").upper()
    if sym not in _watched:
        return
    row = {k: payload.get(k) for k in _PRINT_KEYS}
    try:
        ts = float(row["ts"])
    except (TypeError, ValueError):
        return
    with _lock:
        ring = _rings.get(sym)
        if ring is None:
            return                     # left the watched set while this print was on its way
        ring.append(row)
        while ring and ts - float(ring[0]["ts"]) > AGENT_WAKE_RING_SEC:
            _since[sym] = max(_since.get(sym, 0.0), float(ring.popleft()["ts"]))
    _wake()


def book_in(symbol: str) -> None:
    """A live book changed (the depth handler). Called on the IB loop."""
    if (symbol or "").upper() in _watched:
        _wake()


def prints(symbol: str, since: float) -> list[dict[str, Any]] | None:
    """The live prints after ``since``, or None when the ring does not reach back that far (ask the archive)."""
    sym = symbol.upper()
    with _lock:
        ring = _rings.get(sym)
        start = _since.get(sym)
        if ring is None or start is None or start > since:
            return None
        return [dict(r) for r in ring if float(r["ts"]) > since]


def tail(symbol: str) -> tuple[float, list[dict[str, Any]]] | None:
    """``(since, prints)``: every live print the ring holds and the time it holds them from; None when not watched."""
    sym = symbol.upper()
    with _lock:
        ring, start = _rings.get(sym), _since.get(sym)
        if ring is None or start is None:
            return None
        return start, [dict(r) for r in ring]


def price_prints(symbol: str, after: float) -> list[tuple[float, float]]:
    """``(ts, price)`` of the live prints after ``after`` that set a price (the archive's writer may not have them
    yet); none when the ring does not reach back that far."""
    from sale_conditions import row_sets_price

    out = []
    for row in prints(symbol, after) or []:
        try:
            if row_sets_price(row):
                out.append((float(row["ts"]), float(row["price"])))
        except (TypeError, ValueError):
            continue
    return out
