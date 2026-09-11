"""
IBKR IB singleton connection manager.

Connects to a user-managed IB Gateway process.
Nova does not auto-login (IBKR Mobile 2FA still requires the user).
Users may start/focus Gateway via POST /api/ibkr/launch-gateway (header double-click).

Port selection uses IBKR_GATEWAY_MODE (live→4001 default, paper→4002 fallback),
independent of IBKR_ORDERS_ENABLED / IBKR_LIVE_TRADING_CONFIRMED (see ibkr.safety).

Self-heal follows the listening Gateway (probe-based): preferred dark +
alternate up attaches and persists mode (refuse, timeout-on-dark, or pre-dial
probe). Timeout while preferred still listens is not heal-eligible (Error 326 /
wedged handshake). After every connect, managedAccounts must match the mode.

Intentional Paper↔Live switches set sticky intent in gateway_heal (not a
timer) so a failed switch cannot silently heal to the other mode mid-switch.
Spend gates stay in ibkr.safety — heal never unlocks orders.

State:
  _ib / _mode / _broker_account_kind — updated atomically via _set_session
  _enabled  -- False when IBKR_ENABLED env var is absent/false (safe default)
  _wake_reconnect — Event to interrupt reconnect_loop sleep on user request
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    from ib_async import IB
    _IB_AVAILABLE = True
except ImportError:
    IB = None  # type: ignore[assignment,misc]
    _IB_AVAILABLE = False
    logger.warning("ib_async not installed — IBKR module disabled")

from constants import (
    IBKR_AUTH_BACKOFF_SEC_INITIAL,
    IBKR_HOST,
    IBKR_PAPER_PORT,
    IBKR_LIVE_PORT,
    IBKR_CLIENT_ID,
    IBKR_MARKET_DATA_TYPE_DELAYED,
    IBKR_MARKET_DATA_TYPE_LIVE,
)
from ibkr import account_kind as _account_kind
from ibkr import client_connect as _connect
from ibkr import safety as _safety
from ibkr import session_errors as _session_errors
from ibkr import session_state as _session
from ibkr.client_bridge import run_coro as run_coro  # noqa: F401 -- public re-export
from ibkr.errors import StaleIbkrSessionError  # noqa: F401 -- re-export for tests/callers
from runtime_state import get_runtime_state as _get_runtime_state

# Backward-compat aliases (session_reconnect / tests use client._accept_*)
_read_managed_account_ids = _account_kind.read_managed_account_ids
_accept_connected_session = _account_kind.accept_connected_session

# ── Module-level state ─────────────────────────────────────────────────────────
_ib: "IB | None" = None
_mode: str = "disconnected"
_enabled: bool = False
_broker_account_kind: str = "unknown"
_reconnect_task: asyncio.Task | None = None
_loop: asyncio.AbstractEventLoop | None = None  # captured at startup() — where IB lives
_wake_reconnect: asyncio.Event | None = None
# Set after READY requests live market data (None until first successful READY).
_market_data_type: int | None = None
# Public SoT reason for status / ops (see session_snapshot / ibkr_status).
_session_reason: str = "disabled"
# Auth-backoff when preferred port is open but connect times out (Authenticating).
_auth_backoff_sec: float = float(IBKR_AUTH_BACKOFF_SEC_INITIAL)


def get_market_data_type() -> int | None:
    """Last requested IB market-data type, or None before first READY."""
    return _market_data_type


def set_session_reason(reason: str) -> None:
    """Publish the usable-session SoT reason string (status / diagnostics)."""
    global _session_reason
    _session_reason = str(reason or "unknown")


def session_reason() -> str:
    return _session_reason


def unavailable_detail(what: str = "IBKR") -> str:
    """Honest one-liner when get_ib() is None -- transport vs session not usable."""
    label = (what or "IBKR").strip() or "IBKR"
    if not is_connected():
        return f"{label} transport down -- Gateway not connected"
    reason = session_reason() or "unknown"
    return f"{label} session not usable ({reason})"


def _set_session(*, mode: str, broker_account_kind: str) -> None:
    """Atomically update connection mode + account kind (split-brain guard)."""
    global _mode, _broker_account_kind
    _mode = mode
    _broker_account_kind = broker_account_kind


def _clear_sticky_bridge_error_on_ready() -> None:
    """Drop any ``ibkr_bridge_last_error`` recorded while the session was
    down/degraded (see PROBLEM_LOG 2026-07-23 sticky-banner-after-reconnect).

    A disconnect-window failure (``ib=none``) must not outlive reconnect —
    once the session reaches READY, movers/L1 are live again, so an old
    error string left over from the outage would otherwise paint Integrity
    fail red indefinitely until the next successful movers refresh (or a
    full API restart). This makes reconnect self-heal immediately.
    """
    try:
        state = _get_runtime_state()
    except Exception:
        return
    if getattr(state, "ibkr_bridge_last_error", ""):
        state.ibkr_bridge_last_error = ""
        state.ibkr_bridge_last_error_ts = 0.0


async def _on_session_ready(ib: Any, *, reason: str) -> None:
    """Side effects that must run at every READY transition (G1/G2/G4).

    Clears zombie L1 ownership maps left over from the prior connection,
    installs the session-level errorEvent hook, and requests live market data.
    """
    global _market_data_type
    try:
        from ibkr import ticks as _ticks

        await _ticks.clear_all_subscriptions(reason=reason)
    except Exception:
        logger.exception("IBKR: clear_all_subscriptions failed on READY (%s)", reason)
    try:
        from ibkr import discovery as _discovery

        _discovery.clear_inflight_scan_reqids(reason=reason)
    except Exception:
        logger.exception("IBKR: clear_inflight_scan_reqids failed on READY (%s)", reason)
    try:
        _session_errors.install_error_hook(ib)
    except Exception:
        logger.exception("IBKR: session_errors hook install failed on READY (%s)", reason)
    try:
        _session_errors.reset_session_md_flags()
        ib.reqMarketDataType(int(IBKR_MARKET_DATA_TYPE_LIVE))
        _market_data_type = int(IBKR_MARKET_DATA_TYPE_LIVE)
        logger.info(
            "IBKR: requested market data type %s (%s)",
            _market_data_type,
            reason,
        )
    except Exception:
        logger.exception("IBKR: reqMarketDataType failed on READY (%s)", reason)


def maybe_fallback_to_delayed_market_data() -> bool:
    """If Error 10089 blocked live API MD, switch to delayed (type 3).

    Safe to call from manager loops (not from errorEvent handlers). Returns
    True when a downgrade request was issued this call.
    """
    global _market_data_type
    if not _session_errors.live_market_data_blocked():
        return False
    if _market_data_type == int(IBKR_MARKET_DATA_TYPE_DELAYED):
        return False
    ib = get_ib()
    if ib is None or not is_ready():
        return False
    try:
        ib.reqMarketDataType(int(IBKR_MARKET_DATA_TYPE_DELAYED))
        _market_data_type = int(IBKR_MARKET_DATA_TYPE_DELAYED)
        logger.warning(
            "IBKR: fell back to delayed market data type %s "
            "(live API entitlement missing — Error 10089)",
            _market_data_type,
        )
        return True
    except Exception:
        logger.exception("IBKR: delayed market data fallback failed")
        return False


def _ensure_wake_event() -> asyncio.Event:
    global _wake_reconnect
    if _wake_reconnect is None:
        _wake_reconnect = asyncio.Event()
    return _wake_reconnect


def wake_reconnect_loop() -> None:
    """Interrupt reconnect_loop sleep so a mode switch/reconnect dials now."""
    ev = _wake_reconnect
    if ev is not None:
        ev.set()


async def _sleep_reconnect(delay: float) -> None:
    """Sleep until delay elapses or wake_reconnect_loop() fires."""
    ev = _ensure_wake_event()
    ev.clear()
    try:
        await asyncio.wait_for(ev.wait(), timeout=max(0.0, delay))
    except asyncio.TimeoutError:
        pass


def _resolve_config() -> tuple[bool, str, int, str, int]:
    """Return (enabled, host, port, mode_label, client_id) from env, never raises."""
    enabled = os.environ.get("IBKR_ENABLED", "false").lower() in ("1", "true", "yes")
    host = os.environ.get("IBKR_HOST", IBKR_HOST)
    mode_label = _safety.gateway_mode()
    if mode_label == "live":
        port = int(os.environ.get("IBKR_LIVE_PORT", str(IBKR_LIVE_PORT)))
    else:
        port = int(os.environ.get("IBKR_PAPER_PORT", str(IBKR_PAPER_PORT)))
    try:
        client_id = int(os.environ.get("IBKR_CLIENT_ID", str(IBKR_CLIENT_ID)))
    except (TypeError, ValueError):
        client_id = int(IBKR_CLIENT_ID)
    return enabled, host, port, mode_label, client_id


def is_enabled() -> bool:
    return _enabled


def is_connected() -> bool:
    """Raw transport status — True as soon as the socket handshake completes,
    even while Nova is still validating account kind / warming caches. Use
    ``is_ready()`` (or ``get_ib()``) to gate actual market-data/account work."""
    return _ib is not None and _ib.isConnected()


def is_ready() -> bool:
    """True only after account-kind validation + cache warm-up finished (see
    ibkr/session_state.py). This is the gate ``get_ib()`` uses."""
    return _session.is_ready() and is_connected()


def current_generation() -> int:
    """Monotonic counter bumped every time a session reaches READY. Callers
    that bridge work across threads (see run_coro) use this to detect a
    disconnect/reconnect that happened mid-call."""
    return _session.generation()


def session_snapshot() -> dict[str, Any]:
    """Diagnostic snapshot for /readyz and PROBLEM_LOG-style evidence."""
    from ibkr import ib_scheduler as _ib_scheduler
    from ibkr import session_reconnect as _reconnect
    from ibkr import session_usable as _session_usable

    usable = is_ready()
    task = _reconnect_task
    return {
        "state": _session.state(),
        "generation": _session.generation(),
        "ready": usable,
        "usable": usable,
        "connected": is_connected(),
        "transport_up": is_connected(),
        "reason": _session_reason,
        "unusable_since": _session_errors.unusable_since(),
        "last_connectivity_code": _session_errors.last_connectivity_code(),
        "mode": account_mode(),
        "enabled": _enabled,
        # Diagnostics for the exact freeze this instrumentation was added
        # for (PROBLEM_LOG 2026-08-31) -- one query instead of an hour of
        # log archaeology next time.
        "earn_in_flight": _session_usable.earn_in_flight(),
        "ib_cold_inflight": _ib_scheduler.inflight_label() or None,
        "dialer_alive": task is not None and not task.done(),
        "dialer_heartbeat_age_sec": _reconnect.dialer_heartbeat_age_sec(),
    }


def account_mode() -> str:
    """One of: 'paper', 'live', 'disconnected' (port/env label, not account type)."""
    if not is_connected():
        return "disconnected"
    return _mode


def broker_account_kind() -> str:
    """paper | live | mixed | unknown — from IB managedAccounts after connect."""
    if not is_connected():
        return "unknown"
    return _broker_account_kind


def get_ib() -> "IB | None":
    """Return the IB instance once Nova considers the session READY, else None.

    Gated on ``is_ready()`` (not just raw transport) so scanner/L1/chart/
    account consumers cannot issue commands while account-kind validation or
    cache warm-up is still running (see PROBLEM_LOG 2026-07-23). Internal
    connect/warm-up code in this module bridges around this gate by holding
    a direct reference to ``_ib`` instead of calling ``get_ib()``.
    """
    if is_ready():
        return _ib
    return None


def _safe_disconnect(ib: "IB | None") -> None:
    _connect.safe_disconnect(ib)


async def _attempt_connect(
    ib: "IB", host: str, port: int, client_id: int,
) -> tuple[bool, str]:
    return await _connect.attempt_connect(ib, host, port, client_id)


async def _try_connect_alternate_port(
    ib: "IB",
    host: str,
    preferred_mode: str,
    client_id: int,
    preferred_reason: str,
) -> str | None:
    """Test-facing wrapper — heal logic lives in client_connect."""
    return await _connect.try_connect_alternate_port(
        ib,
        host,
        preferred_mode,
        client_id,
        preferred_reason,
        accept_session=_accept_connected_session,
    )


async def _maybe_heal_from_port_probes(
    ib: "IB",
    host: str,
    preferred_mode: str,
    client_id: int,
) -> str | None:
    """Follow-Gateway fast path when preferred TCP is dark and alternate listens."""
    return await _connect.maybe_heal_from_port_probes(
        ib,
        host,
        preferred_mode,
        client_id,
        accept_session=_accept_connected_session,
    )


async def _handle_transport_up_unusable(mode_label: str) -> None:
    """Test-facing wrapper — recovery lives in session_reconnect."""
    from ibkr import session_reconnect as _reconnect

    import ibkr.client as _self

    await _reconnect.handle_transport_up_unusable(_self, mode_label)


async def reconnect_loop() -> None:
    """Background dialer — implementation in ``session_reconnect``."""
    from ibkr.session_reconnect import reconnect_loop as _loop

    await _loop()


def reload_env_from_dotenv() -> dict[str, str]:
    """Reload root .env into os.environ (override=True). Returns resolved config."""
    from dotenv import load_dotenv
    from paths import env_file_path

    load_dotenv(env_file_path(), override=True)
    enabled, host, port, mode_label, client_id = _resolve_config()
    return {
        "enabled": str(enabled),
        "host": host,
        "port": str(port),
        "gateway_mode": mode_label,
        "client_id": str(client_id),
    }


async def force_reconnect() -> dict:
    """Disconnect and await usable — implementation in ``client_ops``."""
    from ibkr.client_ops import force_reconnect as _force

    return await _force()


async def request_gateway_mode(mode: str) -> dict:
    """User-initiated Paper↔Live switch — implementation in ``client_ops``."""
    from ibkr.client_ops import request_gateway_mode as _switch

    return await _switch(mode)


async def startup() -> None:
    """Called on the IB connect-loop. Starts reconnect as an IB-loop task."""
    from ibkr.loop_supervisor import assert_ib_loop, get_loop, is_ib_loop, is_started, on_ib

    if is_started() and not is_ib_loop():
        await on_ib(startup(), timeout=30.0, label="startup")
        return
    global _reconnect_task, _loop
    assert_ib_loop()
    _loop = get_loop() or asyncio.get_running_loop()
    _ensure_wake_event()
    if _reconnect_task is not None and not _reconnect_task.done():
        return
    _reconnect_task = asyncio.create_task(reconnect_loop())
    logger.info("IBKR client task started (IB connect-loop)")


def reconnect_task() -> "asyncio.Task | None":
    """The dialer task -- read by session_watchdog to detect dead/frozen."""
    return _reconnect_task


def restart_reconnect_task() -> None:
    """Force-respawn the dialer (session_watchdog recovery only). Cancels any
    existing task first; safe even if it is the one that is stuck, since
    cancelling a suspended await does not require it to be responsive."""
    global _reconnect_task
    if _reconnect_task is not None and not _reconnect_task.done():
        _reconnect_task.cancel()
    _reconnect_task = asyncio.create_task(reconnect_loop())
    logger.warning("IBKR client task force-respawned (session watchdog recovery)")


async def shutdown() -> None:
    """Called from lifespan. Cancels reconnect loop and disconnects."""
    global _reconnect_task, _ib
    if _reconnect_task:
        _reconnect_task.cancel()
        try:
            await _reconnect_task
        except asyncio.CancelledError:
            pass
        _reconnect_task = None
    if _ib and _ib.isConnected():
        _ib.disconnect()
    _session.set_disconnected()
    logger.info("IBKR client shut down")
