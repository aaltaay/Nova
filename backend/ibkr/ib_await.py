"""Bounded await for ib_async request futures that cannot leak a stray cancel.

ib_async single-flights positions / completedOrders / accountUpdates. When
``IB.connectAsync``'s own sync ``wait_for`` times out on one of them, it
cancels that shared future but leaves the registry entry live, so the next
caller attaches to the already-cancelled future and gets ``CancelledError``
even though nobody cancelled *its* task. Uncaught, that silently killed the
reconnect dialer mid-warm-up (PROBLEM_LOG 2026-09-19).
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable

from ibkr.errors import StaleIbRequestError


async def await_ib_request(aw: Awaitable[Any], *, timeout: float) -> Any:
    """``asyncio.wait_for`` that turns a foreign cancel into ``StaleIbRequestError``.

    A real cancel of the calling task (``task.cancelling() > 0``) still
    propagates; only a cancel that came from a stale ib_async future is
    converted, so ordinary ``except Exception`` handlers log it.
    """
    try:
        return await asyncio.wait_for(aw, timeout=timeout)
    except asyncio.CancelledError:
        task = asyncio.current_task()
        if task is not None and task.cancelling():
            raise
        raise StaleIbRequestError(
            "ib_async returned an already-cancelled request "
            "(an earlier sync request timed out; Gateway has not answered it yet)"
        ) from None
