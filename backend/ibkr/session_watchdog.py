"""Independent IB-loop watchdog for the IBKR session (ADR 010).

Spawned once at bootstrap as a sibling task to observability.ib_loop_lag, on
the same IB loop as the dialer it watches (session_reconnect.reconnect_loop).
Proof this survives a frozen dialer: the loop-lag sampler is exactly this
kind of sibling task, and it kept sampling every ~2s the entire 7+ hours the
dialer sat frozen on 2026-08-31 (see PROBLEM_LOG). A watchdog that lives
*inside* the dialer task -- as the old stuck-unusable check did -- cannot
fire once that task itself is the thing that froze.

Two independent checks, every IBKR_SESSION_WATCHDOG_INTERVAL_SEC:
  1. Stuck unusable with transport up (Error 1100, no 1101/1102 restore) --
     moved here from session_reconnect.handle_transport_up_unusable.
  2. Dead or frozen dialer task (task.done(), or no _reconnect_once
     iteration in IBKR_DIALER_HEARTBEAT_STALE_SEC) -- force-reset the
     session and respawn reconnect_loop.

Deliberately does not try to diagnose *which* await is stuck (a lock, a
cold_slot acquire, an ib_async request that swallowed cancellation, ...). A
fresh IB object plus a fresh dialer task is the one remedy that is correct
regardless of the cause, and it never touches the Gateway process itself --
only Nova's side of the socket.
"""
from __future__ import annotations

import asyncio
import logging
import time

from ibkr import session_errors as _session_errors
from ibkr import session_state as _session

logger = logging.getLogger(__name__)


async def run() -> None:
    """Sibling task entrypoint -- spawn via loop_supervisor.spawn_ib."""
    from ibkr import client as client_mod

    while True:
        try:
            # Local import (not module-level) so tests can monkeypatch these
            # per-case -- same pattern as ibkr/account.py's timeouts.
            from constants_ibkr import IBKR_SESSION_WATCHDOG_INTERVAL_SEC

            await asyncio.sleep(IBKR_SESSION_WATCHDOG_INTERVAL_SEC)
            _check_stuck_unusable(client_mod)
            _check_dialer_heartbeat(client_mod)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("IBKR session watchdog iteration crashed -- continuing")


def _force_reset_session(client_mod: object, *, reason: str) -> None:
    """Discard the current IB object + session state. Never touches Gateway
    itself -- only Nova's socket/session bookkeeping."""
    client_mod.set_session_reason(reason)  # type: ignore[attr-defined]
    try:
        client_mod._safe_disconnect(client_mod._ib)  # type: ignore[attr-defined]
    except Exception:
        logger.debug("IBKR watchdog: disconnect during reset failed", exc_info=True)
    client_mod._ib = client_mod.IB()  # type: ignore[attr-defined]
    client_mod._set_session(  # type: ignore[attr-defined]
        mode="disconnected", broker_account_kind="unknown",
    )
    _session.set_disconnected()


def _check_stuck_unusable(client_mod: object) -> None:
    from constants_ibkr import IBKR_UNUSABLE_FORCE_RECONNECT_SEC

    if not client_mod.is_connected():  # type: ignore[attr-defined]
        return
    if client_mod.is_ready():  # type: ignore[attr-defined]
        return
    since = _session_errors.unusable_since()
    if since is None:
        return
    stuck_for = time.time() - float(since)
    if stuck_for < float(IBKR_UNUSABLE_FORCE_RECONNECT_SEC):
        return
    logger.error(
        "IBKR watchdog: session stuck unusable for %.1fs with transport up -- "
        "forcing disconnect + recreate (threshold=%.1fs)",
        stuck_for,
        float(IBKR_UNUSABLE_FORCE_RECONNECT_SEC),
    )
    _force_reset_session(client_mod, reason="force_reconnect_stuck_unusable")
    client_mod.wake_reconnect_loop()  # type: ignore[attr-defined]


def _check_dialer_heartbeat(client_mod: object) -> None:
    from constants_ibkr import IBKR_DIALER_HEARTBEAT_STALE_SEC
    from ibkr import session_reconnect as _reconnect

    task = client_mod.reconnect_task()  # type: ignore[attr-defined]
    age = _reconnect.dialer_heartbeat_age_sec()
    dead = task is None or task.done()
    frozen = age is not None and age >= float(IBKR_DIALER_HEARTBEAT_STALE_SEC)
    if not dead and not frozen:
        return
    logger.error(
        "IBKR watchdog: dialer %s (heartbeat_age=%s) -- forcing session reset "
        "and respawning reconnect_loop",
        "dead" if dead else "frozen",
        f"{age:.1f}s" if age is not None else "never",
    )
    _force_reset_session(client_mod, reason="force_respawn_dead_dialer")
    client_mod.restart_reconnect_task()  # type: ignore[attr-defined]
