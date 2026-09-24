"""Single-flight path that promotes a connected IB session to Nova usable.

``earn_usable`` warms account caches, fences mid-sync revoke (Error 1100),
bumps generation via ``set_ready``, then runs READY side effects. Completed
orders are deliberately not part of that warm (D-057) -- they are fetched in
the background after READY by ``ibkr.completed_orders_warm``. Used by
initial connect, self-heal, and 1101/1102 restore — never stack concurrent
warm-ups (anti API_WEDGED).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from ibkr import line_session as _line_session
from ibkr import session_state as _session

logger = logging.getLogger(__name__)

_earn_lock: asyncio.Lock | None = None
_earn_in_flight = False


def _lock() -> asyncio.Lock:
    global _earn_lock
    if _earn_lock is None:
        _earn_lock = asyncio.Lock()
    return _earn_lock


def earn_in_flight() -> bool:
    return _earn_in_flight


async def earn_usable(ib: Any, reason: str) -> tuple[bool, str]:
    """Warm caches → READY → session-ready side effects. Single-flighted.

    Returns ``(ok, detail)``. Does not issue work if ``ib`` is missing or
    transport is already down. If usable is revoked mid-SYNCHRONIZING
    (Error 1100), aborts without calling ``set_ready``.
    """
    global _earn_in_flight
    if ib is None:
        return False, "ib_none"

    async with _lock():
        _earn_in_flight = True
        try:
            return await _earn_usable_locked(ib, reason)
        finally:
            _earn_in_flight = False


async def _earn_usable_locked(ib: Any, reason: str) -> tuple[bool, str]:
    from ibkr import account as _account
    from ibkr import completed_orders_warm as _completed_orders_warm
    from ibkr.client import (
        _clear_sticky_bridge_error_on_ready,
        _on_session_ready,
        set_session_reason,
    )
    from ibkr import session_errors as _session_errors
    # Local import (not the constants.py barrel) so tests can monkeypatch
    # this deadline per-case -- same pattern as ibkr/account.py's timeouts.
    from constants_ibkr import IBKR_EARN_USABLE_TIMEOUT_SEC

    try:
        transport_up = bool(ib.isConnected())
    except Exception:
        transport_up = False
    if not transport_up:
        # Never leave SYNCHRONIZING sticky after a dead socket -- status would
        # claim "synchronizing" while transport_connected=false (desk thinks
        # login/2FA is needed even when Gateway is already up).
        if _session.state() in (_session.SYNCHRONIZING, _session.CONNECTING, _session.READY):
            _session.set_disconnected()
        set_session_reason("disconnected")
        return False, "transport_down"

    _session.set_synchronizing()
    set_session_reason("synchronizing")
    logger.info("IBKR: earn_usable begin (%s)", reason)

    async def _warm() -> None:
        # Completed orders are deliberately NOT here (D-057): a Gateway that
        # stops answering reqCompletedOrders would hold READY for the full
        # earn_usable deadline, and the desk would read that as a login
        # problem. They are fetched after READY by completed_orders_warm.
        await _account.refresh_positions_cache(ib)
        from ibkr.account_stream import ensure_account_updates

        await ensure_account_updates(ib)

    try:
        await asyncio.wait_for(_warm(), timeout=float(IBKR_EARN_USABLE_TIMEOUT_SEC))
    except TimeoutError:
        # Each call has its own internal bound (positions / completed-orders
        # timeout, cold_slot acquire timeout) -- this overall deadline is
        # belt-and-suspenders for the case where one of those is bypassed
        # (see PROBLEM_LOG 2026-08-31). Unlike a caught request failure below,
        # do not promote to READY on top of a warm-up that never finished --
        # leave unusable and let session_watchdog force-reset the session.
        logger.exception(
            "IBKR: earn_usable warm-up exceeded overall deadline (%.1fs, %s) -- "
            "aborting, watchdog will force-reset",
            float(IBKR_EARN_USABLE_TIMEOUT_SEC), reason,
        )
        _session_errors.stamp_unusable()
        return False, "warmup_deadline_exceeded"
    except Exception as exc:
        logger.warning(
            "IBKR: earn_usable warm-up raised (%s): %s", reason, exc, exc_info=True,
        )
        # Best-effort warm continues to fence check — empty caches still fail closed.

    # Fence: 1100 / disconnect during warm must not promote to READY.
    if _session.state() != _session.SYNCHRONIZING:
        logger.warning(
            "IBKR: earn_usable aborted — state=%s after warm (%s)",
            _session.state(),
            reason,
        )
        _session_errors.stamp_unusable()
        return False, "revoked_during_sync"

    try:
        if not ib.isConnected():
            set_session_reason("disconnected")
            _session.set_degraded()
            _session_errors.stamp_unusable()
            return False, "transport_lost"
    except Exception:
        set_session_reason("disconnected")
        return False, "transport_lost"

    gen = _session.set_ready()
    _clear_sticky_bridge_error_on_ready()
    # History after READY, never before it (D-057). Fire-and-forget: a Gateway
    # that never answers reqCompletedOrders must not delay a usable desk.
    _completed_orders_warm.schedule(ib)
    await _on_session_ready(ib, reason=f"{reason} generation {gen}")
    # The last session's tape / depth lines died with it; the HTTP loop lets them go and asks again (#562).
    _line_session.on_session_ready(gen)
    _session_errors.clear_unusable_stamp()
    # Drop a stale restore flag if we earned usable another way.
    _session_errors.take_restore_pending()
    set_session_reason("ok")
    logger.info("IBKR: session READY via earn_usable (generation %d, %s)", gen, reason)
    return True, "ok"


def reset_for_tests() -> None:
    """Test isolation — drop lock state between cases."""
    global _earn_lock, _earn_in_flight
    _earn_lock = None
    _earn_in_flight = False
    from ibkr import completed_orders_warm as _completed_orders_warm

    _completed_orders_warm.reset_for_testing()
