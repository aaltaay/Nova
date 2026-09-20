"""Which IB connection has a loaded completed-orders history.

``closed_orders()`` is built from ``ib.trades()``, and orders that finished
before this API session only appear there after ``reqCompletedOrders``
answers. When the Gateway never answers it (PROBLEM_LOG 2026-09-19), "not in
closed orders" is not evidence of anything, so ``execution.startup_sweep``
checks this before treating absence as an outcome.

Held as a weakref to the IB object: every reconnect builds a fresh ``IB()``,
which therefore never inherits an earlier connection's success.

Listeners (``add_load_listener``) let a caller act the moment history arrives
— ``execution.startup_sweep`` uses one to resolve the rows it had to leave
``unverified`` (D-077) without waiting for the next API restart. Registration
points the other way on purpose: ibkr must not import execution.
"""
from __future__ import annotations

import logging
import weakref
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_loaded_on: weakref.ref | None = None
_listeners: list[Callable[[], None]] = []


def add_load_listener(callback: Callable[[], None]) -> None:
    """Call ``callback`` after the next successful completed-orders load."""
    if callback not in _listeners:
        _listeners.append(callback)


def remove_load_listener(callback: Callable[[], None]) -> None:
    if callback in _listeners:
        _listeners.remove(callback)


def mark_loaded(ib: Any) -> None:
    global _loaded_on
    _loaded_on = weakref.ref(ib)
    for callback in list(_listeners):
        try:
            callback()
        except Exception:
            # A listener must never break the IBKR request that just
            # succeeded -- the history is loaded either way.
            logger.exception("completed_orders_state: load listener failed")


def loaded_for(ib: Any) -> bool:
    ref = _loaded_on
    return ib is not None and ref is not None and ref() is ib


def reset_for_testing() -> None:
    global _loaded_on
    _loaded_on = None
    _listeners.clear()
