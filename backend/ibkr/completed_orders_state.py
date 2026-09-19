"""Which IB connection has a loaded completed-orders history.

``closed_orders()`` is built from ``ib.trades()``, and orders that finished
before this API session only appear there after ``reqCompletedOrders``
answers. When the Gateway never answers it (PROBLEM_LOG 2026-09-19), "not in
closed orders" is not evidence of anything, so ``execution.startup_sweep``
checks this before treating absence as an outcome.

Held as a weakref to the IB object: every reconnect builds a fresh ``IB()``,
which therefore never inherits an earlier connection's success.
"""
from __future__ import annotations

import weakref
from typing import Any

_loaded_on: weakref.ref | None = None


def mark_loaded(ib: Any) -> None:
    global _loaded_on
    _loaded_on = weakref.ref(ib)


def loaded_for(ib: Any) -> bool:
    ref = _loaded_on
    return ib is not None and ref is not None and ref() is ib


def reset_for_testing() -> None:
    global _loaded_on
    _loaded_on = None
