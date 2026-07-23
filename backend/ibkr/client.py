"""
IBKR IB singleton connection manager.

Connects to a user-managed IB Gateway process.
Nova does not auto-login (IBKR Mobile 2FA still requires the user).
Users may start/focus Gateway via POST /api/ibkr/launch-gateway (header double-click).

Port selection uses IBKR_GATEWAY_MODE (paper→4002, live→4001), independent
of IBKR_ORDERS_ENABLED / IBKR_LIVE_TRADING_CONFIRMED (see ibkr.safety).

Self-heal is bidirectional when the preferred port is hard-refused and the
alternate port answers (never on timeout / Error 326). After every connect,
managedAccounts are classified and must match the mode being established.

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
from concurrent.futures import TimeoutError as _FuturesTimeoutError
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
    IBKR_HOST,
    IBKR_PAPER_PORT,
    IBKR_LIVE_PORT,
    IBKR_CLIENT_ID,
    IBKR_CONNECT_TIMEOUT_SEC,
    IBKR_RECONNECT_DELAY_SEC,
)
from ibkr import account_kind as _account_kind
from ibkr import client_connect as _connect
from ibkr import gateway_heal as _heal
from ibkr import safety as _safety
from ibkr import session_state as _session
from ibkr.errors import StaleIbkrSessionError
from runtime_state import get_runtime_state as _get_runtime_state

# ── Module-level state ─────────────────────────────────────────────────────────
_ib: "IB | None" = None
_mode: str = "disconnected"
_enabled: bool = False
_broker_account_kind: str = "unknown"
_reconnect_task: asyncio.Task | None = None
_loop: asyncio.AbstractEventLoop | None = None  # captured at startup() — where IB lives
_wake_reconnect: asyncio.Event | None = None


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
    return {
        "state": _session.state(),
        "generation": _session.generation(),
        "ready": is_ready(),
        "connected": is_connected(),
        "mode": account_mode(),
        "enabled": _enabled,
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


def _read_managed_account_ids(ib: "IB") -> list[str]:
    """Normalize ib_async managedAccounts() to a list of account id strings."""
    try:
        raw = ib.managedAccounts()
    except Exception:
        logger.warning("IBKR: managedAccounts() failed", exc_info=True)
        return []
    if raw is None:
        return []
    if isinstance(raw, str):
        return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(a).strip() for a in raw if str(a).strip()]
    s = str(raw).strip()
    return [s] if s else []


def _accept_connected_session(ib: "IB", mode_label: str) -> tuple[bool, str]:
    """
    Classify managedAccounts; require kind to match ``mode_label``.
    Updates ``_broker_account_kind``. Returns (ok, reason). On failure
    caller must disconnect.
    """
    global _broker_account_kind
    ids = _read_managed_account_ids(ib)
    kind = _account_kind.classify_managed_accounts(ids)
    _broker_account_kind = kind
    ok, reason = _account_kind.accounts_match_mode(kind, mode_label)
    if not ok:
        logger.error(
            "IBKR: refusing session — %s (accounts=%s mode=%s)",
            reason,
            ids,
            mode_label,
        )
        return False, reason
    logger.info(
        "IBKR: session accounts kind=%s ids=%s mode=%s",
        kind,
        ids,
        mode_label,
    )
    return True, ""


def run_coro(coro, timeout: float, *, label: str = "") -> Any:
    """
    Bridge: run an ib_async coroutine on the loop IB is connected to, blocking
    the calling thread until done. ib_async's IB instance is bound to whichever
    event loop called connectAsync(), so scan-loop code running in a
    ThreadPoolExecutor worker (see main.py's run_in_executor calls) cannot
    await IBKR coroutines directly — this bridges that gap safely.

    On timeout, cancels the submitted future instead of abandoning it — an
    uncancelled ``run_coroutine_threadsafe`` future keeps running against the
    IBKR session after the caller gives up, so a reconnect can race a still-
    live old-generation request (see PROBLEM_LOG 2026-07-23). Cancellation
    propagates into the coroutine as ``CancelledError`` at its next await.

    Raises ``StaleIbkrSessionError`` if the IBKR session disconnected and
    reconnected (generation changed) while this call was in flight — the
    result reflects a session the caller no longer owns and must not be
    applied.
    """
    if _loop is None or not _loop.is_running():
        raise RuntimeError("IBKR event loop not running (client not started)")
    tag = f" [{label}]" if label else ""
    generation_before = _session.generation()
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    try:
        result = future.result(timeout=timeout)
    except _FuturesTimeoutError:
        cancelled = future.cancel()
        logger.warning(
            "IBKR: run_coro timed out after %.1fs%s (cancel %s)",
            timeout, tag, "accepted" if cancelled else "too late — already running/done",
        )
        raise
    if _session.generation() != generation_before:
        logger.warning(
            "IBKR: run_coro%s result from stale generation (%s -> %s) — discarding",
            tag, generation_before, _session.generation(),
        )
        raise StaleIbkrSessionError(
            f"session reconnected during call{tag} "
            f"(generation {generation_before} -> {_session.generation()})"
        )
    return result


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


async def reconnect_loop() -> None:
    """Background task: keep connecting while IBKR_ENABLED is set.

    Re-reads gateway mode/port each attempt so a .env change to paper/live
    takes effect without requiring a full process restart (after reload_env).
    On preferred-port refuse only, self-heals to the alternate reachable port.
    """
    global _ib, _enabled

    if not _IB_AVAILABLE:
        logger.warning("IBKR module enabled but ib_async not installed — skipping")
        return

    _ensure_wake_event()
    _ib = IB()

    while True:
        enabled, host, port, mode_label, client_id = _resolve_config()
        _enabled = enabled

        if not _enabled:
            _set_session(mode="disconnected", broker_account_kind="unknown")
            _session.set_disconnected()
            if _ib.isConnected():
                _ib.disconnect()
            await _sleep_reconnect(IBKR_RECONNECT_DELAY_SEC)
            continue

        if not _ib.isConnected():
            if _session.state() == _session.READY:
                # Was ready, transport dropped without going through the
                # explicit disconnect paths below — label it honestly rather
                # than silently jumping straight back to "connecting".
                _session.set_degraded()
            logger.info(
                "IBKR: attempting connect to %s:%s (%s, clientId=%s)",
                host,
                port,
                mode_label,
                client_id,
            )
            _session.set_connecting()
            ok, reason = await _attempt_connect(_ib, host, port, client_id)
            if ok:
                _session.set_synchronizing()
                session_ok, session_reason = _accept_connected_session(_ib, mode_label)
                if session_ok:
                    _set_session(mode=mode_label, broker_account_kind=_broker_account_kind)
                    _heal.record_connect_outcome(
                        "connected", reason="ok", mode=mode_label,
                    )
                    logger.info(
                        "IBKR: connected in %s mode (orders still gated by safety.py)",
                        mode_label,
                    )
                    from ibkr import account as _account

                    # Pass the just-connected ib directly (not get_ib(), which
                    # gates on READY) — these warm-ups are what earn READY.
                    await _account.refresh_positions_cache(_ib)
                    await _account.refresh_completed_orders_cache(_ib)
                    gen = _session.set_ready()
                    _clear_sticky_bridge_error_on_ready()
                    logger.info("IBKR: session READY (generation %d)", gen)
                else:
                    logger.error(
                        "IBKR: disconnecting after paper-pin reject: %s",
                        session_reason,
                    )
                    _safe_disconnect(_ib)
                    _ib = IB()
                    _set_session(mode="disconnected", broker_account_kind="unknown")
                    _session.set_disconnected()
                    _heal.record_connect_outcome(
                        "failed", reason=session_reason or "account_kind_mismatch",
                    )
                    await _sleep_reconnect(IBKR_RECONNECT_DELAY_SEC)
                    continue
            else:
                # Recreate IB() so a half-open protocol state cannot pin the loop.
                _safe_disconnect(_ib)
                _ib = IB()
                _session.set_connecting()
                healed = await _try_connect_alternate_port(
                    _ib, host, mode_label, client_id, reason,
                )
                if healed:
                    _session.set_synchronizing()
                    _set_session(mode=healed, broker_account_kind=_broker_account_kind)
                    logger.info(
                        "IBKR: connected in %s mode after self-heal "
                        "(orders still gated by safety.py)",
                        healed,
                    )
                    from ibkr import account as _account

                    await _account.refresh_positions_cache(_ib)
                    await _account.refresh_completed_orders_cache(_ib)
                    gen = _session.set_ready()
                    _clear_sticky_bridge_error_on_ready()
                    logger.info("IBKR: session READY after self-heal (generation %d)", gen)
                    continue
                _set_session(mode="disconnected", broker_account_kind="unknown")
                _session.set_disconnected()
                _heal.record_connect_outcome("failed", reason=reason)
                _safe_disconnect(_ib)
                _ib = IB()
                await _sleep_reconnect(IBKR_RECONNECT_DELAY_SEC)
                continue
        elif _mode != mode_label:
            # Mode flipped (paper↔live) in env while connected — drop and reconnect.
            logger.warning(
                "IBKR: gateway_mode changed %s → %s; reconnecting", _mode, mode_label,
            )
            _ib.disconnect()
            _set_session(mode="disconnected", broker_account_kind="unknown")
            _session.set_disconnected()
            continue
        await _sleep_reconnect(5)


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
    """Disconnect and let reconnect_loop pick up the current .env port/mode."""
    global _ib
    cfg = reload_env_from_dotenv()
    if _ib is not None and _ib.isConnected():
        _ib.disconnect()
    _set_session(mode="disconnected", broker_account_kind="unknown")
    _session.set_disconnected()
    wake_reconnect_loop()
    # Brief wait for the background loop to attempt connect.
    await asyncio.sleep(min(IBKR_RECONNECT_DELAY_SEC, 2.0) + 1.0)
    return {
        **cfg,
        "connected": is_connected(),
        "mode": account_mode(),
        "broker_account_kind": broker_account_kind(),
        "spend_status": _safety.status_snapshot()["spend_status"],
    }


async def request_gateway_mode(mode: str) -> dict:
    """
    User-initiated Paper↔Live Gateway switch (StockViewAccountModeCapsule).

    Persists IBKR_GATEWAY_MODE, disconnects, and wakes reconnect_loop to dial
    the new port. Sets sticky intentional mode so a refused live port surfaces
    honestly instead of silently self-healing to paper. Never touches
    IBKR_LIVE_TRADING_CONFIRMED — spend stays locked until armed separately.
    """
    global _ib

    target: str = "live" if str(mode).strip().lower() == "live" else "paper"
    if str(mode).strip().lower() not in ("paper", "live"):
        return {"ok": False, "error": f"invalid mode {mode!r} (must be paper or live)"}

    if not _enabled:
        return {
            "ok": False,
            "error": "IBKR_ENABLED is not set — cannot connect to any Gateway",
            "requested_mode": target,
        }

    preferred_port = _heal.port_for_mode(target)
    persisted = _heal.persist_gateway_mode(target)  # type: ignore[arg-type]
    _heal.apply_runtime_gateway_mode(target)  # type: ignore[arg-type]
    _heal.set_intentional_mode(target)  # type: ignore[arg-type]

    if _ib is not None and _ib.isConnected():
        _ib.disconnect()
    _set_session(mode="disconnected", broker_account_kind="unknown")
    _session.set_disconnected()
    wake_reconnect_loop()

    # reconnect_loop picks up the new port — wake + poll briefly.
    deadline = IBKR_CONNECT_TIMEOUT_SEC + 3.0
    waited = 0.0
    step = 0.5
    while waited < deadline and not is_connected():
        await asyncio.sleep(step)
        waited += step

    connected = is_connected()
    kind = broker_account_kind()
    mode_now = account_mode()
    error: str | None = None

    if not connected:
        error = (
            f"Could not connect to the {target} Gateway on port {preferred_port} "
            f"— start IB Gateway logged into the {target} account with the API "
            "enabled on that port, then try again."
        )
        _heal.record_connect_outcome("failed", reason="switch_connect_failed")
    elif target == "live" and kind != "live":
        # Defensive: a paper-only Gateway session should never answer on the
        # live port, but refuse loudly rather than pretend Live if it does.
        bad_kind = kind
        logger.error(
            "IBKR: gateway-mode switch to live connected but "
            "broker_account_kind=%s (expected live) — disconnecting",
            bad_kind,
        )
        if _ib is not None and _ib.isConnected():
            _ib.disconnect()
        _set_session(mode="disconnected", broker_account_kind="unknown")
        _session.set_disconnected()
        connected = False
        mode_now = "disconnected"
        kind = "unknown"
        error = (
            "Connected on the live port but the logged-in account reports as "
            f"{bad_kind!r}, not live — refusing to switch (disconnected)."
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


async def startup() -> None:
    """Called from lifespan bootstrap. Starts reconnect loop as a background task."""
    global _reconnect_task, _loop
    _loop = asyncio.get_running_loop()
    _ensure_wake_event()
    if _reconnect_task is not None and not _reconnect_task.done():
        return
    _reconnect_task = asyncio.create_task(reconnect_loop())
    logger.info("IBKR client task started")


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
