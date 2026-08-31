"""One IB-loop cold scheduler (ADR 010).

Replaces historical_gate + discovery._snapshot_lock + completed-orders lock.
Interactive chart preempts droppable cold work. In-flight work finishes
(one request); queued droppable jobs raise ColdDropped.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from ibkr.loop_supervisor import assert_ib_loop

_lock: asyncio.Lock | None = None
_interactive_depth = 0
_inflight_label = ""


class ColdDropped(Exception):
    """Droppable cold work aborted because interactive/hot needs the slot."""


class ColdSlotTimeout(Exception):
    """Lock acquire exceeded IBKR_COLD_SLOT_ACQUIRE_TIMEOUT_SEC -- a stranded
    holder (crashed/cancelled without releasing) or a stuck IB request is
    blocking every future cold job. Caller must treat this as a failed
    warm-up, not retry the acquire inline (see PROBLEM_LOG 2026-08-31)."""


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def interactive_busy() -> bool:
    return _interactive_depth > 0


def inflight_label() -> str:
    return _inflight_label


def reset_for_testing() -> None:
    global _lock, _interactive_depth, _inflight_label
    _lock = None
    _interactive_depth = 0
    _inflight_label = ""


@asynccontextmanager
async def cold_slot(
    *,
    label: str,
    interactive: bool = False,
    droppable: bool = True,
) -> AsyncIterator[None]:
    """Single-flight IB cold slot. Must be awaited on the IB loop once started."""
    global _interactive_depth, _inflight_label
    assert_ib_loop()
    if interactive:
        _interactive_depth += 1
    try:
        if not interactive and droppable and _interactive_depth > 0:
            raise ColdDropped("interactive chart has priority")
        # Local import of the domain module (not the constants.py barrel) so
        # tests can monkeypatch the constant per-case -- same pattern as
        # ibkr/account.py's completed-orders timeout.
        from constants_ibkr import IBKR_COLD_SLOT_ACQUIRE_TIMEOUT_SEC

        lock = _get_lock()
        try:
            await asyncio.wait_for(
                lock.acquire(), timeout=float(IBKR_COLD_SLOT_ACQUIRE_TIMEOUT_SEC),
            )
        except TimeoutError as exc:
            raise ColdSlotTimeout(
                f"cold_slot acquire timed out after "
                f"{float(IBKR_COLD_SLOT_ACQUIRE_TIMEOUT_SEC):.1f}s "
                f"(label={label!r}, current_holder={_inflight_label!r})"
            ) from exc
        try:
            if not interactive and droppable and _interactive_depth > 0:
                raise ColdDropped("interactive chart has priority")
            _inflight_label = label
            yield
        finally:
            _inflight_label = ""
            lock.release()
    finally:
        if interactive:
            _interactive_depth = max(0, _interactive_depth - 1)
