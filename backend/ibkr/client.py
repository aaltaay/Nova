"""
IBKR IB singleton connection manager.

Connects to a user-managed IB Gateway process.
Nova does not auto-login (IBKR Mobile 2FA still requires the user).
Users may start/focus Gateway via POST /api/ibkr/launch-gateway (header double-click).

Port selection uses IBKR_GATEWAY_MODE (paper→4002, live→4001), independent
of IBKR_ORDERS_ENABLED / IBKR_LIVE_TRADING_CONFIRMED (see ibkr.safety).

Self-heal is fail-safe toward paper only (never paper→live). After every
connect, managedAccounts are classified; paper mode refuses live accounts.

State:
  _ib       -- the ib_async.IB() instance (always exists, may be disconnected)
  _mode     -- "paper" | "live" | "disconnected"
  _enabled  -- False when IBKR_ENABLED env var is absent/false (safe default)
  _broker_account_kind -- paper | live | mixed | unknown (from managedAccounts)
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
    IBKR_HOST,
    IBKR_PAPER_PORT,
    IBKR_LIVE_PORT,
    IBKR_CLIENT_ID,
    IBKR_CONNECT_TIMEOUT_SEC,
    IBKR_RECONNECT_DELAY_SEC,
)
from ibkr import account_kind as _account_kind
from ibkr import gateway_heal as _heal
from ibkr import safety as _safety

# ── Module-level state ─────────────────────────────────────────────────────────
_ib: "IB | None" = None
_mode: str = "disconnected"
_enabled: bool = False
_broker_account_kind: str = "unknown"
_reconnect_task: asyncio.Task | None = None
_loop: asyncio.AbstractEventLoop | None = None  # captured at startup() — where IB lives


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
    return _ib is not None and _ib.isConnected()


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
    """Return the IB instance if connected, else None."""
    if is_connected():
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
    Classify managedAccounts; enforce paper pin. Updates ``_broker_account_kind``.
    Returns (ok, reason). On failure caller must disconnect.
    """
    global _broker_account_kind
    ids = _read_managed_account_ids(ib)
    kind = _account_kind.classify_managed_accounts(ids)
    _broker_account_kind = kind
    # Prefer env gateway_mode — heal may have just flipped it to paper.
    target = _safety.gateway_mode()
    if mode_label == "paper" or target == "paper":
        ok, reason = _account_kind.paper_mode_accounts_ok(kind)
        if not ok:
            logger.error(
                "IBKR PAPER PIN: refusing session — %s (accounts=%s mode=%s)",
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


def run_coro(coro, timeout: float) -> Any:
    """
    Bridge: run an ib_async coroutine on the loop IB is connected to, blocking
    the calling thread until done. ib_async's IB instance is bound to whichever
    event loop called connectAsync(), so scan-loop code running in a
    ThreadPoolExecutor worker (see main.py's run_in_executor calls) cannot
    await IBKR coroutines directly — this bridges that gap safely.
    """
    if _loop is None or not _loop.is_running():
        raise RuntimeError("IBKR event loop not running (client not started)")
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=timeout)


def _safe_disconnect(ib: "IB | None") -> None:
    """Best-effort teardown — call even when isConnected() is False (half-open)."""
    if ib is None:
        return
    try:
        ib.disconnect()
    except Exception:
        logger.debug("IBKR: disconnect during reset failed", exc_info=True)


async def _attempt_connect(
    ib: "IB", host: str, port: int, client_id: int,
) -> tuple[bool, str]:
    """Connect with a hard asyncio wall. Returns (ok, failure_reason)."""
    wall = float(IBKR_CONNECT_TIMEOUT_SEC)
    inner = max(1.0, wall - 0.5)
    try:
        await asyncio.wait_for(
            ib.connectAsync(host, port, clientId=client_id, timeout=inner),
            timeout=wall,
        )
        return True, "ok"
    except asyncio.TimeoutError:
        logger.warning(
            "IBKR: connect timed out after %.1fs to %s:%s (clientId=%s) — "
            "Gateway may be wedged or clientId in use (Error 326)",
            wall,
            host,
            port,
            client_id,
        )
        _safe_disconnect(ib)
        return False, _heal.classify_connect_failure(None, timed_out=True)
    except Exception as exc:
        msg = str(exc) or type(exc).__name__
        logger.warning(
            "IBKR: connect failed to %s:%s (clientId=%s): %s",
            host,
            port,
            client_id,
            msg,
        )
        _safe_disconnect(ib)
        return False, _heal.classify_connect_failure(exc, timed_out=False)


async def _try_connect_alternate_port(
    ib: "IB",
    host: str,
    preferred_mode: str,
    client_id: int,
    preferred_reason: str,
) -> str | None:
    """If preferred live port failed, try paper only. Never paper→live."""
    if not _heal.self_heal_enabled():
        return None
    if preferred_reason not in ("refused", "timeout"):
        return None

    alt_mode = _heal.alternate_mode(preferred_mode)
    if not _heal.heal_target_allowed(from_mode=preferred_mode, to_mode=alt_mode):
        logger.warning(
            "IBKR: preferred %s port failed (%s); refusing self-heal to %s "
            "(paper pin — never attach to live automatically)",
            preferred_mode,
            preferred_reason,
            alt_mode,
        )
        return None

    alt_port = _heal.port_for_mode(alt_mode)
    preferred_port = _heal.port_for_mode(preferred_mode)
    logger.info(
        "IBKR: preferred %s:%s failed (%s); trying %s:%s (self-heal→paper only)",
        preferred_mode,
        preferred_port,
        preferred_reason,
        alt_mode,
        alt_port,
    )
    ok, _alt_reason = await _attempt_connect(ib, host, alt_port, client_id)
    if not ok:
        return None

    session_ok, session_reason = _accept_connected_session(ib, alt_mode)
    if not session_ok:
        _safe_disconnect(ib)
        return None

    _heal.apply_runtime_gateway_mode(alt_mode)  # type: ignore[arg-type]
    persisted = _heal.persist_gateway_mode(alt_mode)  # type: ignore[arg-type]
    _heal.record_heal(
        from_mode=preferred_mode,
        to_mode=alt_mode,  # type: ignore[arg-type]
        reason=preferred_reason,
        preferred_port=preferred_port,
        healed_port=alt_port,
        persisted=persisted,
    )
    return alt_mode


async def reconnect_loop() -> None:
    """Background task: keep connecting while IBKR_ENABLED is set.

    Re-reads gateway mode/port each attempt so a .env change to paper/live
    takes effect without requiring a full process restart (after reload_env).
    On preferred live-port refuse/timeout, self-heals to paper only.
    """
    global _ib, _mode, _enabled, _broker_account_kind

    if not _IB_AVAILABLE:
        logger.warning("IBKR module enabled but ib_async not installed — skipping")
        return

    _ib = IB()

    while True:
        enabled, host, port, mode_label, client_id = _resolve_config()
        _enabled = enabled

        if not _enabled:
            _mode = "disconnected"
            _broker_account_kind = "unknown"
            if _ib.isConnected():
                _ib.disconnect()
            await asyncio.sleep(IBKR_RECONNECT_DELAY_SEC)
            continue

        if not _ib.isConnected():
            logger.info(
                "IBKR: attempting connect to %s:%s (%s, clientId=%s)",
                host,
                port,
                mode_label,
                client_id,
            )
            ok, reason = await _attempt_connect(_ib, host, port, client_id)
            if ok:
                session_ok, session_reason = _accept_connected_session(_ib, mode_label)
                if session_ok:
                    _mode = mode_label
                    logger.info(
                        "IBKR: connected in %s mode (orders still gated by safety.py)",
                        mode_label,
                    )
                else:
                    logger.error(
                        "IBKR: disconnecting after paper-pin reject: %s",
                        session_reason,
                    )
                    _safe_disconnect(_ib)
                    _ib = IB()
                    _mode = "disconnected"
                    _broker_account_kind = "unknown"
                    await asyncio.sleep(IBKR_RECONNECT_DELAY_SEC)
                    continue
            else:
                # Recreate IB() so a half-open protocol state cannot pin the loop.
                _safe_disconnect(_ib)
                _ib = IB()
                healed = await _try_connect_alternate_port(
                    _ib, host, mode_label, client_id, reason,
                )
                if healed:
                    _mode = healed
                    logger.info(
                        "IBKR: connected in %s mode after self-heal "
                        "(orders still gated by safety.py)",
                        healed,
                    )
                    continue
                _mode = "disconnected"
                _broker_account_kind = "unknown"
                _safe_disconnect(_ib)
                _ib = IB()
                await asyncio.sleep(IBKR_RECONNECT_DELAY_SEC)
                continue
        elif _mode != mode_label:
            # Mode flipped (paper↔live) in env while connected — drop and reconnect.
            logger.warning(
                "IBKR: gateway_mode changed %s → %s; reconnecting", _mode, mode_label,
            )
            _ib.disconnect()
            _mode = "disconnected"
            _broker_account_kind = "unknown"
            continue
        await asyncio.sleep(5)


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
    global _ib, _mode, _broker_account_kind
    cfg = reload_env_from_dotenv()
    if _ib is not None and _ib.isConnected():
        _ib.disconnect()
    _mode = "disconnected"
    _broker_account_kind = "unknown"
    # Brief wait for the background loop to attempt connect.
    await asyncio.sleep(min(IBKR_RECONNECT_DELAY_SEC, 2.0) + 1.0)
    return {
        **cfg,
        "connected": is_connected(),
        "mode": account_mode(),
        "broker_account_kind": broker_account_kind(),
        "spend_status": _safety.status_snapshot()["spend_status"],
    }


async def startup() -> None:
    """Called from lifespan bootstrap. Starts reconnect loop as a background task."""
    global _reconnect_task, _loop
    _loop = asyncio.get_running_loop()
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
    logger.info("IBKR client shut down")
