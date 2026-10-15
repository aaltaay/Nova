"""Shared local admission for pending and active AllLast requests (#674).

An explicit account budget or a 10190 refusal can bound automatic requests.
Neither local ownership nor a sent cancel proves IBKR's upstream occupancy.
The HTTP loop reserves; IB error callbacks learn limits under the same short lock.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

from constants_ibkr import IBKR_TAPE_MAX_LINES_ENV

logger = logging.getLogger(__name__)
_lock = threading.RLock()


@dataclass(eq=False)
class Reservation:
    symbol: str
    ib: Any
    generation: int
    state: str = "pending"
    sent_count: int = 0


_slots: dict[str, Reservation] = {}
_ib: Any = None
_generation: int | None = None
_learned: int | None = None


def _session() -> None:
    global _ib, _generation, _learned
    from ibkr import client

    ib, gen = client.get_ib(), client.current_generation()
    # get_ib is READY-gated: a temporary outage is not a new connection.
    if gen != _generation or (ib is not None and ib is not _ib):
        _slots.clear()
        _learned = None
        _ib, _generation = ib, gen


def reset_for_tests() -> None:
    global _ib, _generation, _learned
    with _lock:
        _slots.clear()
        _ib, _generation, _learned = None, None, None


def _budget() -> tuple[int | None, str, str | None]:
    raw = os.environ.get(IBKR_TAPE_MAX_LINES_ENV, "").strip()
    configured = None
    if raw:
        try:
            configured = int(raw)
            if configured <= 0:
                raise ValueError("positive integer required")
        except ValueError:
            return 0, "configured", f"{IBKR_TAPE_MAX_LINES_ENV} must be a positive integer"
    if configured is not None and _learned is not None:
        return min(configured, _learned), "configured+refusal", None
    if configured is not None:
        return configured, "configured", None
    return _learned, "refusal" if _learned is not None else "unknown", None


def view() -> dict:
    with _lock:
        _session()
        limit, source, error = _budget()
        return {"limit": limit, "source": source, "used": len(_slots),
                **{state: sorted(s for s, row in _slots.items() if row.state == state)
                   for state in ("pending", "active", "uncertain")},
                "free": None if limit is None else max(0, limit - len(_slots)),
                "error": error}


def available(symbol: str | None = None) -> int | None:
    """None: unknown budget. Joining a held symbol spends no additional tape slot."""
    with _lock:
        state = view()
        row = _slots.get((symbol or "").upper())
        if row is not None and row.state != "uncertain" and not state["error"]:
            return None
        return state["free"]


def reserve(symbol: str, *, automatic: bool) -> tuple[Reservation | None, str | None]:
    with _lock:
        _session()
        limit, _, error = _budget()
        if symbol in _slots:
            return None, f"Tape release for {symbol} is uncertain; waiting for a new IBKR session"
        if automatic and (error or (limit is not None and len(_slots) >= limit)):
            return None, error or f"Shared AllLast tape capacity full ({len(_slots)}/{limit}); auto-record waits"
        row = Reservation(symbol, _ib, _generation)
        _slots[symbol] = row
        return row, None


def current(row: Reservation) -> bool:
    from ibkr import client

    with _lock:
        _session()
        return _slots.get(row.symbol) is row and client.get_ib() is row.ib


def requested(row: Reservation) -> None:
    with _lock:
        if current(row):
            row.state = "active"
            row.sent_count = sum(r.state != "pending" for r in _slots.values())


def abandon(row: Reservation) -> None:
    with _lock:
        _session()
        if _slots.get(row.symbol) is row and row.state == "pending":
            _slots.pop(row.symbol)


def released(symbol: str, generation: int | None, *, sent: bool) -> None:
    with _lock:
        _session()
        row = _slots.get(symbol)
        if row is not None and row.generation == generation:
            if sent:
                _slots.pop(symbol)
            else:
                row.state = "uncertain"


def adopt(symbol: str) -> None:
    """Count a line IBKR kept on 1102 after line_session restamps it."""
    with _lock:
        _session()
        if symbol not in _slots:
            _slots[symbol] = Reservation(symbol, _ib, _generation, "active")
        for row in _slots.values():
            row.sent_count = len(_slots)


def refused(symbol: str) -> None:
    """A matched current request got 10190. Learn before deferred HTTP-loop cleanup."""
    global _learned
    with _lock:
        _session()
        row = _slots.get(symbol)
        if row is None or row.state != "active":
            return
        ceiling = max(0, row.sent_count - 1)
        _learned = ceiling if _learned is None else min(_learned, ceiling)
        logger.warning("IBKR tape: 10190 on %s; automatic local admission ceiling now %s "
                       "(account capacity and upstream release remain unproven)", symbol, _learned)
