"""IBKR reconnect_loop + soft-blip / auth-backoff recovery.

Owns the background dialer: connect → earn_usable, 1101/1102 restore, and
Authenticating auth-backoff. Stuck-unusable force-reconnect and dead/frozen-
dialer recovery live in ``ibkr.session_watchdog`` -- a sibling IB-loop task,
deliberately NOT this module, because a watchdog inside the task it watches
cannot fire once that task itself is what froze (PROBLEM_LOG 2026-08-31).

Mutates ``ibkr.client`` session globals (single owner of the IB singleton).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from constants import (
    IBKR_AUTH_BACKOFF_SEC_INITIAL,
    IBKR_AUTH_BACKOFF_SEC_MAX,
    IBKR_RECONNECT_DELAY_SEC,
)
from ibkr import attach_retry as _attach
from ibkr import gateway_heal as _heal
from ibkr import session_errors as _session_errors
from ibkr import session_state as _session
from ibkr import session_usable as _session_usable

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Dialer heartbeat -- stamped at the top of every _reconnect_once iteration.
# session_watchdog reads this (dialer_heartbeat_age_sec) to tell a normally
# busy dialer apart from one that is dead or frozen mid-await.
_last_iteration_ts: float = 0.0


def dialer_heartbeat_age_sec() -> float | None:
    """Seconds since the last _reconnect_once iteration started, or None
    before the dialer has ever run (nothing to judge yet)."""
    if _last_iteration_ts <= 0.0:
        return None
    return time.monotonic() - _last_iteration_ts


def reset_heartbeat_for_testing() -> None:
    global _last_iteration_ts
    _last_iteration_ts = 0.0


def reset_auth_backoff(client_mod: object) -> None:
    client_mod._auth_backoff_sec = float(IBKR_AUTH_BACKOFF_SEC_INITIAL)  # type: ignore[attr-defined]


def bump_auth_backoff(client_mod: object) -> float:
    delay = float(client_mod._auth_backoff_sec)  # type: ignore[attr-defined]
    client_mod._auth_backoff_sec = min(  # type: ignore[attr-defined]
        float(IBKR_AUTH_BACKOFF_SEC_MAX),
        max(float(IBKR_AUTH_BACKOFF_SEC_INITIAL), delay * 2.0),
    )
    return delay


async def handle_transport_up_unusable(client_mod: object, mode_label: str) -> None:
    """Act on soft blip while the TCP session is still up.

    Stuck-unusable force-reconnect no longer lives here -- see module
    docstring. This function only attempts the 1101/1102 restore and, when
    there is nothing to restore, waits briefly for the sibling watchdog
    (which owns the stuck-for-N-seconds decision) rather than duplicating
    that timer inside the task the watchdog is supposed to be independent of.
    """
    restore = _session_errors.take_restore_pending()
    if restore is not None:
        client_mod.set_session_reason(  # type: ignore[attr-defined]
            "connectivity_data_lost" if restore == "data_lost" else "connectivity_restored"
        )
        logger.info(
            "IBKR: connectivity restore (%s) -- earn_usable (mode=%s)",
            restore,
            mode_label,
        )
        ok, detail = await _session_usable.earn_usable(
            client_mod._ib,  # type: ignore[attr-defined]
            f"connectivity_restored_{restore}",
        )
        if ok:
            reset_auth_backoff(client_mod)
            return
        logger.warning(
            "IBKR: earn_usable after %s failed (%s) -- watchdog owns stuck-unusable timing",
            restore,
            detail,
        )

    if client_mod.is_ready():  # type: ignore[attr-defined]
        return

    if _session_errors.unusable_since() is None:
        _session_errors.stamp_unusable()

    await client_mod._sleep_reconnect(1.0)  # type: ignore[attr-defined]


def _open_port_stall_reason() -> str:
    """``second_factor_pending`` while IBC shows an unanswered 2FA prompt, else ``gateway_authenticating``."""
    try:
        from ibkr import second_factor as _second_factor

        if _second_factor.current_state().pending:
            return "second_factor_pending"
    except Exception:
        logger.debug("IBKR: second-factor state unreadable for the attach ledger", exc_info=True)
    return "gateway_authenticating"


async def auth_backoff_sleep(
    client_mod: object, host: str, port: int, mode_label: str,
) -> None:
    # ADR 021: never retry faster than either schedule -- the existing auth
    # backoff or the attach ledger (which turns a stall into a human step).
    delay = max(bump_auth_backoff(client_mod), _attach.next_delay_sec())
    client_mod.set_session_reason("gateway_authenticating")  # type: ignore[attr-defined]
    logger.warning(
        "IBKR: preferred %s:%s open but connect timed out (%s) -- "
        "auth-backoff %.1fs (clientId kept; no alternate-port heal)",
        mode_label,
        port,
        host,
        delay,
    )
    await client_mod._sleep_reconnect(delay)  # type: ignore[attr-defined]


async def reconnect_loop() -> None:
    """Background task: keep connecting while IBKR_ENABLED is set."""
    from ibkr import client as client_mod

    if not client_mod._IB_AVAILABLE:
        logger.warning("IBKR module enabled but ib_async not installed -- skipping")
        return

    client_mod._ensure_wake_event()
    client_mod._ib = client_mod.IB()

    while True:
        try:
            await _reconnect_once(client_mod)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "IBKR: reconnect_loop iteration crashed -- resetting session and retrying"
            )
            try:
                client_mod._safe_disconnect(client_mod._ib)
            except Exception:
                logger.debug("IBKR: disconnect after loop crash failed", exc_info=True)
            try:
                client_mod._ib = client_mod.IB()
                client_mod._set_session(
                    mode="disconnected", broker_account_kind="unknown",
                )
                _session.set_disconnected()
                client_mod.set_session_reason("reconnect_loop_error")
            except Exception:
                logger.debug("IBKR: session reset after loop crash failed", exc_info=True)
            await client_mod._sleep_reconnect(IBKR_RECONNECT_DELAY_SEC)


async def _reconnect_once(client_mod: object) -> None:
    """One reconnect_loop iteration (extracted so crashes cannot kill the dialer)."""
    global _last_iteration_ts
    _last_iteration_ts = time.monotonic()
    enabled, host, port, mode_label, client_id = client_mod._resolve_config()  # type: ignore[attr-defined]
    client_mod._enabled = enabled  # type: ignore[attr-defined]

    if not client_mod._enabled:  # type: ignore[attr-defined]
        client_mod._set_session(  # type: ignore[attr-defined]
            mode="disconnected", broker_account_kind="unknown",
        )
        _session.set_disconnected()
        client_mod.set_session_reason("disabled")  # type: ignore[attr-defined]
        if client_mod._ib.isConnected():  # type: ignore[attr-defined]
            client_mod._ib.disconnect()  # type: ignore[attr-defined]
        await client_mod._sleep_reconnect(IBKR_RECONNECT_DELAY_SEC)  # type: ignore[attr-defined]
        return

    if not client_mod._ib.isConnected():  # type: ignore[attr-defined]
        # READY → DEGRADED; SYNCHRONIZING must not stick after TCP drop.
        if _session.state() == _session.READY:
            _session.set_degraded()
            _session_errors.stamp_unusable()
            client_mod.set_session_reason("disconnected")  # type: ignore[attr-defined]
        elif _session.state() == _session.SYNCHRONIZING:
            _session.set_disconnected()
            _session_errors.stamp_unusable()
            client_mod.set_session_reason("disconnected")  # type: ignore[attr-defined]
        _session.set_connecting()
        client_mod.set_session_reason("connecting")  # type: ignore[attr-defined]

        # Follow-Gateway: if preferred is dark and the other mode is up, attach
        # there immediately instead of waiting out a preferred-port timeout.
        probe_healed = await client_mod._maybe_heal_from_port_probes(  # type: ignore[attr-defined]
            client_mod._ib, host, mode_label, client_id,  # type: ignore[attr-defined]
        )
        if probe_healed:
            client_mod._set_session(  # type: ignore[attr-defined]
                mode=probe_healed,
                broker_account_kind=client_mod._broker_account_kind,  # type: ignore[attr-defined]
            )
            logger.info(
                "IBKR: connected in %s mode after probe self-heal "
                "(orders still gated by safety.py)",
                probe_healed,
            )
            earned, earn_detail = await _session_usable.earn_usable(
                client_mod._ib, "self_heal",  # type: ignore[attr-defined]
            )
            if earned:
                reset_auth_backoff(client_mod)
                _attach.clear(reason="ready")
                return
            logger.error(
                "IBKR: earn_usable failed after probe self-heal (%s)",
                earn_detail,
            )
            _attach.record_attempt("earn_usable_failed", port=port, detail=str(earn_detail)[:200])
            client_mod._safe_disconnect(client_mod._ib)  # type: ignore[attr-defined]
            client_mod._ib = client_mod.IB()  # type: ignore[attr-defined]
            client_mod._set_session(  # type: ignore[attr-defined]
                mode="disconnected", broker_account_kind="unknown",
            )
            _session.set_disconnected()
            await client_mod._sleep_reconnect(IBKR_RECONNECT_DELAY_SEC)  # type: ignore[attr-defined]
            return

        logger.info(
            "IBKR: attempting connect to %s:%s (%s, clientId=%s)",
            host,
            port,
            mode_label,
            client_id,
        )
        ok, reason = await client_mod._attempt_connect(  # type: ignore[attr-defined]
            client_mod._ib, host, port, client_id,  # type: ignore[attr-defined]
        )
        if ok:
            session_ok, reject_reason = client_mod._accept_connected_session(  # type: ignore[attr-defined]
                client_mod._ib, mode_label,  # type: ignore[attr-defined]
            )
            if session_ok:
                kind = client_mod._broker_account_kind  # type: ignore[attr-defined]
                mode_now = kind if kind in ("paper", "live") else mode_label
                client_mod._set_session(  # type: ignore[attr-defined]
                    mode=mode_now,
                    broker_account_kind=kind,
                )
                _heal.record_connect_outcome(
                    "connected", reason="ok", mode=mode_now,
                )
                logger.info(
                    "IBKR: connected in %s mode (orders still gated by safety.py)",
                    mode_now,
                )
                earned, earn_detail = await _session_usable.earn_usable(
                    client_mod._ib, "connect",  # type: ignore[attr-defined]
                )
                if earned:
                    reset_auth_backoff(client_mod)
                    _attach.clear(reason="ready")
                    return
                logger.error(
                    "IBKR: earn_usable failed after connect (%s)",
                    earn_detail,
                )
                _attach.record_attempt("earn_usable_failed", port=port, detail=str(earn_detail)[:200])
                client_mod._safe_disconnect(client_mod._ib)  # type: ignore[attr-defined]
                client_mod._ib = client_mod.IB()  # type: ignore[attr-defined]
                client_mod._set_session(  # type: ignore[attr-defined]
                    mode="disconnected", broker_account_kind="unknown",
                )
                _session.set_disconnected()
                await client_mod._sleep_reconnect(IBKR_RECONNECT_DELAY_SEC)  # type: ignore[attr-defined]
                return

            logger.error(
                "IBKR: disconnecting after paper-pin reject: %s",
                reject_reason,
            )
            client_mod._safe_disconnect(client_mod._ib)  # type: ignore[attr-defined]
            client_mod._ib = client_mod.IB()  # type: ignore[attr-defined]
            client_mod._set_session(  # type: ignore[attr-defined]
                mode="disconnected", broker_account_kind="unknown",
            )
            _session.set_disconnected()
            _heal.record_connect_outcome(
                "failed", reason=reject_reason or "account_kind_mismatch",
            )
            _attach.record_attempt("account_kind_mismatch", port=port, detail=reject_reason)
            await client_mod._sleep_reconnect(IBKR_RECONNECT_DELAY_SEC)  # type: ignore[attr-defined]
            return

        client_mod._safe_disconnect(client_mod._ib)  # type: ignore[attr-defined]
        client_mod._ib = client_mod.IB()  # type: ignore[attr-defined]
        _session.set_connecting()

        if reason == "client_id_in_use":
            client_mod.set_session_reason("client_id_in_use")  # type: ignore[attr-defined]
            client_mod._set_session(  # type: ignore[attr-defined]
                mode="disconnected", broker_account_kind="unknown",
            )
            _session.set_disconnected()
            _heal.record_connect_outcome("failed", reason="client_id_in_use")
            _attach.record_attempt("client_id_in_use", port=port)
            logger.error(
                "IBKR: clientId %s already in use (Error 326) -- another Nova "
                "API is holding the Gateway slot. One process on :8000 only.",
                client_id,
            )
            await client_mod._sleep_reconnect(IBKR_RECONNECT_DELAY_SEC)  # type: ignore[attr-defined]
            return

        if reason == "timeout":
            from ibkr.port_diagnostics import probe_port

            if probe_port(host, port):
                client_mod._set_session(  # type: ignore[attr-defined]
                    mode="disconnected", broker_account_kind="unknown",
                )
                _session.set_disconnected()
                _heal.record_connect_outcome(
                    "failed", reason="gateway_authenticating",
                )
                _attach.record_attempt(_open_port_stall_reason(), port=port)
                await auth_backoff_sleep(client_mod, host, port, mode_label)
                return

        healed = await client_mod._try_connect_alternate_port(  # type: ignore[attr-defined]
            client_mod._ib, host, mode_label, client_id, reason,  # type: ignore[attr-defined]
        )
        if healed:
            client_mod._set_session(  # type: ignore[attr-defined]
                mode=healed,
                broker_account_kind=client_mod._broker_account_kind,  # type: ignore[attr-defined]
            )
            logger.info(
                "IBKR: connected in %s mode after self-heal "
                "(orders still gated by safety.py)",
                healed,
            )
            earned, earn_detail = await _session_usable.earn_usable(
                client_mod._ib, "self_heal",  # type: ignore[attr-defined]
            )
            if earned:
                reset_auth_backoff(client_mod)
                _attach.clear(reason="ready")
                return
            logger.error(
                "IBKR: earn_usable failed after self-heal (%s)",
                earn_detail,
            )
            _attach.record_attempt("earn_usable_failed", port=port, detail=str(earn_detail)[:200])
            client_mod._safe_disconnect(client_mod._ib)  # type: ignore[attr-defined]
            client_mod._ib = client_mod.IB()  # type: ignore[attr-defined]
        client_mod._set_session(  # type: ignore[attr-defined]
            mode="disconnected", broker_account_kind="unknown",
        )
        _session.set_disconnected()
        _heal.record_connect_outcome("failed", reason=reason)
        client_mod._safe_disconnect(client_mod._ib)  # type: ignore[attr-defined]
        client_mod._ib = client_mod.IB()  # type: ignore[attr-defined]
        await client_mod._sleep_reconnect(IBKR_RECONNECT_DELAY_SEC)  # type: ignore[attr-defined]
        return

    if client_mod._mode != mode_label:  # type: ignore[attr-defined]
        logger.warning(
            "IBKR: gateway_mode changed %s -> %s; reconnecting",
            client_mod._mode,  # type: ignore[attr-defined]
            mode_label,
        )
        client_mod._ib.disconnect()  # type: ignore[attr-defined]
        client_mod._set_session(  # type: ignore[attr-defined]
            mode="disconnected", broker_account_kind="unknown",
        )
        _session.set_disconnected()
        client_mod.set_session_reason("disconnected")  # type: ignore[attr-defined]
        return

    # 1101/1102 must re-earn even if still READY (bump gen + _on_session_ready).
    if (
        _session_errors.peek_restore_pending() is not None
        or not client_mod.is_ready()  # type: ignore[attr-defined]
    ):
        await handle_transport_up_unusable(client_mod, mode_label)
        return

    await client_mod._sleep_reconnect(5)  # type: ignore[attr-defined]
