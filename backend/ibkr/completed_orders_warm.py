"""Fetch completed orders AFTER READY, never inside the connect path (D-057).

``reqCompletedOrders`` is the one IBKR request a Gateway can silently stop
answering for hours after a Gateway<->IBKR server reconnect while positions,
open orders, executions and account updates all answer in under a second
(live probe 2026-09-19). Both places Nova used to ask for it blocked
something the desk needs:

- ``IB.connectAsync`` awaits it with the rest of its startup sync, so the
  handshake burned the whole connect budget and the dialer reported
  ``gateway_authenticating`` -- the desk told the trader to log in when the
  login was fine.
- ``session_usable.earn_usable``'s warm-up awaited it before ``set_ready``,
  so READY itself waited on history nobody needs to trade.

So: READY first, history second. ``schedule`` starts a background task on the
IB loop that asks a few times with backoff; whatever it does not get,
``completed_orders_health.reprobe_loop`` keeps asking for every
``IBKR_COMPLETED_ORDERS_REPROBE_SEC``, the desk shows the amber
"not answering since HH:MM" row, and ``execution.startup_sweep`` leaves
previous-run rows ``unverified`` instead of calling them abandoned (#301).

One task at a time: a new connection cancels the previous connection's task,
so a wedged Gateway can never stack warms (anti API_WEDGED).
"""
from __future__ import annotations

import asyncio
import logging
import weakref
from typing import Any

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None
_target: weakref.ref | None = None


def _cancel_running() -> None:
    global _task
    task = _task
    _task = None
    if task is None or task.done():
        return
    try:
        task.cancel()
    except Exception:
        # Loop already closed (test teardown) -- nothing left to stop.
        logger.debug("IBKR: completed-orders warm cancel failed", exc_info=True)


def schedule(ib: Any) -> None:
    """Start (or restart) the post-READY warm for ``ib``. Never awaits IBKR."""
    global _task, _target
    if ib is None:
        return
    _cancel_running()
    _target = weakref.ref(ib)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop (unit test / sync caller) -- the re-probe loop still covers
        # history; never make READY depend on this.
        logger.debug("IBKR: completed-orders warm not scheduled (no loop)")
        return
    _task = loop.create_task(_warm_loop(ib), name="ibkr.completed_orders_warm")


async def _warm_loop(ib: Any) -> None:
    from constants_ibkr import IBKR_COMPLETED_ORDERS_WARM_BACKOFF_SEC

    from ibkr import account as _account
    from ibkr import completed_orders_state as _state

    backoff = tuple(IBKR_COMPLETED_ORDERS_WARM_BACKOFF_SEC)
    for attempt in range(len(backoff) + 1):
        if not _still_current(ib):
            return
        try:
            await _account.refresh_completed_orders_cache(ib, force=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            # refresh_completed_orders_cache logs + stamps health itself; a
            # raise here would only kill the retry schedule.
            logger.warning(
                "IBKR: completed-orders warm attempt %d raised", attempt + 1,
                exc_info=True,
            )
        if _state.loaded_for(ib):
            return
        if attempt >= len(backoff):
            break
        await asyncio.sleep(float(backoff[attempt]))
    logger.warning(
        "IBKR: completed orders still unanswered after %d post-READY attempts "
        "-- the desk shows the stuck warning and the re-probe loop keeps "
        "asking; Closed Orders may miss pre-session fills until it answers",
        len(backoff) + 1,
    )


def _still_current(ib: Any) -> bool:
    """False once this connection was replaced or the socket went down."""
    ref = _target
    if ref is None or ref() is not ib:
        return False
    try:
        return bool(ib.isConnected())
    except Exception:
        return False


def reset_for_testing() -> None:
    global _target
    _cancel_running()
    _target = None
