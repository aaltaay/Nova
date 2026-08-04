"""User-facing IBKR reconnect / gateway-mode switch helpers.

Extracted from ``client.py`` to keep the connection manager under the
file-size limit. Mutates ``ibkr.client`` session globals.
"""
from __future__ import annotations

import asyncio
import logging

from constants import (
    IBKR_COMPLETED_ORDERS_TIMEOUT_SEC,
    IBKR_CONNECT_TIMEOUT_SEC,
    IBKR_POSITIONS_TIMEOUT_SEC,
)
from ibkr import gateway_heal as _heal
from ibkr import safety as _safety
from ibkr import session_errors as _session_errors
from ibkr import session_state as _session

logger = logging.getLogger(__name__)


async def force_reconnect() -> dict:
    """Disconnect and let reconnect_loop pick up the current .env port/mode.

    Awaits usable (READY) up to connect + warm-up budget so callers see honest
    ``connected`` (= usable), not a premature socket-only result.
    """
    from ibkr import client as c

    cfg = c.reload_env_from_dotenv()
    if c._ib is not None and c._ib.isConnected():
        c._ib.disconnect()
    c._set_session(mode="disconnected", broker_account_kind="unknown")
    _session.set_disconnected()
    c.set_session_reason("connecting")
    _session_errors.stamp_unusable()
    c.wake_reconnect_loop()

    deadline = (
        float(IBKR_CONNECT_TIMEOUT_SEC)
        + float(IBKR_POSITIONS_TIMEOUT_SEC)
        + float(IBKR_COMPLETED_ORDERS_TIMEOUT_SEC)
        + 5.0
    )
    waited = 0.0
    step = 0.5
    while waited < deadline and not c.is_ready():
        await asyncio.sleep(step)
        waited += step

    usable = c.is_ready()
    return {
        **cfg,
        "connected": usable,
        "transport_connected": c.is_connected(),
        "session_reason": c.session_reason(),
        "session_state": _session.state(),
        "session_generation": _session.generation(),
        "mode": c.account_mode(),
        "broker_account_kind": c.broker_account_kind(),
        "spend_status": _safety.status_snapshot()["spend_status"],
    }


async def request_gateway_mode(mode: str) -> dict:
    """User-initiated Paper↔Live Gateway switch (never unlocks spend)."""
    from ibkr import client as c

    target: str = "live" if str(mode).strip().lower() == "live" else "paper"
    if str(mode).strip().lower() not in ("paper", "live"):
        return {"ok": False, "error": f"invalid mode {mode!r} (must be paper or live)"}

    if not c._enabled:
        return {
            "ok": False,
            "error": "IBKR_ENABLED is not set -- cannot connect to any Gateway",
            "requested_mode": target,
        }

    preferred_port = _heal.port_for_mode(target)
    persisted = _heal.persist_gateway_mode(target)  # type: ignore[arg-type]
    _heal.apply_runtime_gateway_mode(target)  # type: ignore[arg-type]
    _heal.set_intentional_mode(target)  # type: ignore[arg-type]

    if c._ib is not None and c._ib.isConnected():
        c._ib.disconnect()
    c._set_session(mode="disconnected", broker_account_kind="unknown")
    _session.set_disconnected()
    c.wake_reconnect_loop()

    deadline = IBKR_CONNECT_TIMEOUT_SEC + 3.0
    waited = 0.0
    step = 0.5
    while waited < deadline and not c.is_connected():
        await asyncio.sleep(step)
        waited += step

    connected = c.is_connected()
    kind = c.broker_account_kind()
    mode_now = c.account_mode()
    error: str | None = None

    if not connected:
        error = (
            f"Could not connect to the {target} Gateway on port {preferred_port} "
            f"-- start IB Gateway logged into the {target} account with the API "
            "enabled on that port, then try again."
        )
        _heal.record_connect_outcome("failed", reason="switch_connect_failed")
    elif target == "live" and kind != "live":
        bad_kind = kind
        logger.error(
            "IBKR: gateway-mode switch to live connected but "
            "broker_account_kind=%s (expected live) -- disconnecting",
            bad_kind,
        )
        if c._ib is not None and c._ib.isConnected():
            c._ib.disconnect()
        c._set_session(mode="disconnected", broker_account_kind="unknown")
        _session.set_disconnected()
        connected = False
        mode_now = "disconnected"
        kind = "unknown"
        error = (
            "Connected on the live port but the logged-in account reports as "
            f"{bad_kind!r}, not live -- refusing to switch (disconnected)."
        )
        _heal.record_connect_outcome("failed", reason="live_account_kind_mismatch")
    else:
        _heal.record_connect_outcome("connected", reason="ok", mode=target)

    return {
        "ok": error is None,
        "error": error,
        "requested_mode": target,
        "preferred_port": preferred_port,
        "persisted": persisted,
        "connected": connected,
        "mode": mode_now,
        "broker_account_kind": kind,
        "spend_status": _safety.status_snapshot()["spend_status"],
        "intentional_gateway_mode": _heal.intentional_mode(),
    }
