"""
IBKR IB singleton connection manager.

Connects to a user-managed IB Gateway process.
Nova does not auto-login (IBKR Mobile 2FA still requires the user).
Users may start/focus Gateway via POST /api/ibkr/launch-gateway (header double-click).

Port selection uses IBKR_GATEWAY_MODE (live->4001 default, paper->4002 fallback),
independent of IBKR_ORDERS_ENABLED / IBKR_LIVE_TRADING_CONFIRMED (see ibkr.safety).

Self-heal follows the listening Gateway (probe-based): preferred dark +
alternate up attaches and persists mode (refuse, timeout-on-dark, or pre-dial
probe). Timeout while preferred still listens is not heal-eligible (Error 326 /
wedged handshake). After every connect, managedAccounts must match the mode.

Intentional Paper<->Live switches set sticky intent in gateway_heal (not a
timer) so a failed switch cannot silently heal to the other mode mid-switch.
Spend gates stay in ibkr.safety -- heal never unlocks orders.

State:
  _ib / _mode / _broker_account_kind -- updated atomically via _set_session
  _enabled  -- False when IBKR_ENABLED env var is absent/false (safe default)
  _wake_reconnect -- Event to interrupt reconnect_loop sleep on user request
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from ib_async import IB
    _IB_AVAILABLE = True
except ImportError:
    IB = None  # type: ignore[assignment,misc]
    _IB_AVAILABLE = False
    logger.warning("ib_async not installed -- IBKR module disabled")

from constants import (
    IBKR_AUTH_BACKOFF_SEC_INITIAL,
    IBKR_MARKET_DATA_TYPE_DELAYED,  # noqa: F401 -- re-export
    IBKR_MARKET_DATA_TYPE_LIVE,  # noqa: F401 -- re-export
)
from ibkr import account_kind as _account_kind
from ibkr import client_connect as _connect
from ibkr import client_ready as _client_ready
from ibkr.client_config import _resolve_config as _resolve_config  # noqa: F401 -- re-export
from ibkr.client_config import reload_env_from_dotenv as reload_env_from_dotenv  # noqa: F401 -- re-export
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
# False until the dialer's first pass has read IBKR_ENABLED (session_reconnect).
_config_loaded: bool = False
_broker_account_kind: str = "unknown"
# IB managedAccounts() of the connected session: what Nova is logged into.
_managed_account_ids: list[str] = []
_reconnect_task: asyncio.Task | None = None
_loop: asyncio.AbstractEventLoop | None = None  # captured at startup() -- where IB lives
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


def _set_session(*, mode: str, broker_account_kind: str, account_ids: list[str] | None = None) -> None:
    """Atomically update connection mode + account kind (split-brain guard).

    ``account_ids`` travels with the kind it was classified from; a session
    that is not connected names no account.
    """
    global _mode, _broker_account_kind, _managed_account_ids
    _mode = mode
    _broker_account_kind = broker_account_kind
    if mode == "disconnected":
        _managed_account_ids = []
    elif account_ids is not None:
        # Callers that only re-state the mode keep the ids the accept step read.
        _managed_account_ids = list(account_ids)


def _clear_sticky_bridge_error_on_ready() -> None:
    """Drop any ``ibkr_bridge_last_error`` recorded while the session was down/degraded."""
    _client_ready.clear_sticky_bridge_error_on_ready(_get_runtime_state)


async def _on_session_ready(ib: Any, *, reason: str) -> None:
    """Side effects that must run at every READY transition (G1/G2/G4)."""
    global _market_data_type
    md_type = await _client_ready.on_session_ready(
        ib, reason=reason, session_errors=_session_errors,
    )
    if md_type is not None:
        _market_data_type = md_type


def maybe_fallback_to_delayed_market_data() -> bool:
    """If Error 10089 blocked live API MD, switch to delayed (type 3)."""
    global _market_data_type
    md_type = _client_ready.fallback_to_delayed_market_data(
        get_ib(),
        ready=is_ready(),
        current_md_type=_market_data_type,
        session_errors=_session_errors,
    )
    if md_type is not None:
        _market_data_type = md_type
        return True
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
    except asyncio.TimeoutError:  # maintainer: allow-swallow the delay elapsing is the normal end of the sleep
        pass


def is_enabled() -> bool:
    """IBKR_ENABLED as this process has it. Until the dialer's first pass has
    read it, the env answers: a client that has not started is not disabled."""
    if _enabled or _config_loaded:
        return _enabled
    return _resolve_config()[0]


def is_starting() -> bool:
    """IBKR_ENABLED is on, but the dialer has not read it yet (API start)."""
    return not _config_loaded and not _enabled and _resolve_config()[0]


def is_connected() -> bool:
    """Raw transport status -- True as soon as the socket handshake completes,
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
    return _client_ready.build_session_snapshot(
        usable=is_ready(),
        connected=is_connected(),
        reason=_session_reason,
        mode=account_mode(),
        enabled=is_enabled(),
        reconnect_task=_reconnect_task,
        session_state=_session,
        session_errors=_session_errors,
    )


def account_mode() -> str:
    """One of: 'paper', 'live', 'disconnected' (port/env label, not account type)."""
    if not is_connected():
        return "disconnected"
    return _mode


def broker_account_kind() -> str:
    """paper | live | mixed | unknown -- from IB managedAccounts after connect."""
    if not is_connected():
        return "unknown"
    return _broker_account_kind


def managed_account_ids() -> list[str]:
    """IB managedAccounts() of the connected session; empty while disconnected."""
    if not is_connected():
        return []
    return list(_managed_account_ids)


def account_id() -> str | None:
    """The account Nova is logged into (first managed account), or None."""
    ids = managed_account_ids()
    return ids[0] if ids else None


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
    """Test-facing wrapper -- heal logic lives in client_connect."""
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
    """Test-facing wrapper -- recovery lives in session_reconnect."""
    from ibkr import session_reconnect as _reconnect
    import ibkr.client as _self

    await _reconnect.handle_transport_up_unusable(_self, mode_label)


async def reconnect_loop() -> None:
    """Background dialer -- implementation in ``session_reconnect``."""
    from ibkr.session_reconnect import reconnect_loop as _loop

    await _loop()


async def force_reconnect() -> dict:
    """Disconnect and await usable -- implementation in ``client_ops``."""
    from ibkr.client_ops import force_reconnect as _force

    return await _force()


async def request_gateway_mode(mode: str) -> dict:
    """User-initiated Paper<->Live switch -- implementation in ``client_ops``."""
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
        except asyncio.CancelledError:  # maintainer: allow-swallow we cancelled this task two lines up
            pass
        _reconnect_task = None
    if _ib and _ib.isConnected():
        _ib.disconnect()
    _session.set_disconnected()
    logger.info("IBKR client shut down")
