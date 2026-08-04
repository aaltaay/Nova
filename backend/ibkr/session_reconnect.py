"""IBKR reconnect_loop + soft-blip / auth-backoff recovery.

Owns the background dialer: connect → earn_usable, 1101/1102 restore,
stuck-unusable force reconnect, and Authenticating auth-backoff.
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
    IBKR_UNUSABLE_FORCE_RECONNECT_SEC,
)
from ibkr import gateway_heal as _heal
from ibkr import session_errors as _session_errors
from ibkr import session_state as _session
from ibkr import session_usable as _session_usable

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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
    """Act on soft blip / stuck unusable while the TCP session is still up."""
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
            "IBKR: earn_usable after %s failed (%s) -- checking stuck watchdog",
            restore,
            detail,
        )

    if client_mod.is_ready():  # type: ignore[attr-defined]
        return

    since = _session_errors.unusable_since()
    if since is None:
        _session_errors.stamp_unusable()
        since = _session_errors.unusable_since() or time.time()
    stuck_for = time.time() - float(since)
    if stuck_for >= float(IBKR_UNUSABLE_FORCE_RECONNECT_SEC):
        logger.error(
            "IBKR session stuck unusable for %.1fs with transport up -- "
            "forcing disconnect + recreate (threshold=%.1fs)",
            stuck_for,
            float(IBKR_UNUSABLE_FORCE_RECONNECT_SEC),
        )
        client_mod.set_session_reason("force_reconnect_stuck_unusable")  # type: ignore[attr-defined]
        client_mod._safe_disconnect(client_mod._ib)  # type: ignore[attr-defined]
        client_mod._ib = client_mod.IB()  # type: ignore[attr-defined]
        client_mod._set_session(  # type: ignore[attr-defined]
            mode="disconnected", broker_account_kind="unknown",
        )
        _session.set_disconnected()
        return

    await client_mod._sleep_reconnect(1.0)  # type: ignore[attr-defined]


async def auth_backoff_sleep(
    client_mod: object, host: str, port: int, mode_label: str,
) -> None:
    delay = bump_auth_backoff(client_mod)
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
        logger.info(
            "IBKR: attempting connect to %s:%s (%s, clientId=%s)",
            host,
            port,
            mode_label,
            client_id,
        )
        _session.set_connecting()
        client_mod.set_session_reason("connecting")  # type: ignore[attr-defined]
        ok, reason = await client_mod._attempt_connect(  # type: ignore[attr-defined]
            client_mod._ib, host, port, client_id,  # type: ignore[attr-defined]
        )
        if ok:
            session_ok, reject_reason = client_mod._accept_connected_session(  # type: ignore[attr-defined]
                client_mod._ib, mode_label,  # type: ignore[attr-defined]
            )
            if session_ok:
                client_mod._set_session(  # type: ignore[attr-defined]
                    mode=mode_label,
                    broker_account_kind=client_mod._broker_account_kind,  # type: ignore[attr-defined]
                )
                _heal.record_connect_outcome(
                    "connected", reason="ok", mode=mode_label,
                )
                logger.info(
                    "IBKR: connected in %s mode (orders still gated by safety.py)",
                    mode_label,
                )
                earned, earn_detail = await _session_usable.earn_usable(
                    client_mod._ib, "connect",  # type: ignore[attr-defined]
                )
                if earned:
                    reset_auth_backoff(client_mod)
                    return
                logger.error(
                    "IBKR: earn_usable failed after connect (%s)",
                    earn_detail,
                )
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
            await client_mod._sleep_reconnect(IBKR_RECONNECT_DELAY_SEC)  # type: ignore[attr-defined]
            return

        client_mod._safe_disconnect(client_mod._ib)  # type: ignore[attr-defined]
        client_mod._ib = client_mod.IB()  # type: ignore[attr-defined]
        _session.set_connecting()

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
                return
            logger.error(
                "IBKR: earn_usable failed after self-heal (%s)",
                earn_detail,
            )
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
