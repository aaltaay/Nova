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
        "spend_status": _safety.status_snapshot(c.broker_account_kind())[
            "spend_status"
        ],
    }


async def request_gateway_mode(mode: str) -> dict:
    """User-initiated Paper↔Live door change (ADR 013). Never unlocks spend.

    Already on that account class -> no-op.
    Target port already up -> reconnect only (no 2FA).
    Target port dark -> start IBC with force_restart (stop both listeners).
    Wrong class on the target port -> replace that port (also force_restart).
    """
    import os

    from constants import IBKR_HOST
    from ibkr import client as c
    from ibkr.launch_gateway import launch_or_focus_gateway
    from ibkr.mode_identity import switch_plan
    from ibkr.port_diagnostics import probe_port

    target: str = "live" if str(mode).strip().lower() == "live" else "paper"
    if str(mode).strip().lower() not in ("paper", "live"):
        return {"ok": False, "error": f"invalid mode {mode!r} (must be paper or live)"}

    if not c._enabled:
        return {
            "ok": False,
            "error": "IBKR_ENABLED is not set -- cannot connect to any Gateway",
            "requested_mode": target,
        }

    kind_now = c.broker_account_kind()
    preferred_port = _heal.port_for_mode(target)
    host = (os.environ.get("IBKR_HOST") or IBKR_HOST).strip() or IBKR_HOST
    target_up = probe_port(host, preferred_port)
    current_port = _heal.port_for_mode(_safety.gateway_mode())
    on_target = bool(c.is_connected() and current_port == preferred_port)
    plan = switch_plan(
        target=target,
        account_kind=kind_now,
        target_port_listening=target_up,
        connected_on_target_port=on_target,
    )

    persisted = _heal.persist_gateway_mode(target)  # type: ignore[arg-type]
    _heal.apply_runtime_gateway_mode(target)  # type: ignore[arg-type]
    _heal.set_intentional_mode(target)  # type: ignore[arg-type]
    # ADR 018: a venue change disarms. Paper<->Live posts here rather than
    # through sim.mode, so without this an armed Paper desk would reconnect as
    # Live still armed and spend on the next keystroke -- the same class of bug
    # as carrying an arm across a restart. Disarm on every door change, even a
    # no-op one: the operator asked for a different desk.
    _safety.set_armed(False, reason=f"gateway mode -> {target}")

    if plan == "noop":
        from ibkr.gateway_trail import append_event as _trail

        _trail(
            actor="operator",
            event="click",
            requested=target,
            kind_before=kind_now,
            kind_after=kind_now,
            plan="noop",
            launch_action="noop",
            switched=True,
            note="already on that IB account class",
        )
        _heal.record_connect_outcome("connected", reason="ok", mode=target)
        return {
            "ok": True,
            "error": None,
            "requested_mode": target,
            "preferred_port": preferred_port,
            "persisted": persisted,
            "connected": True,
            "mode": c.account_mode(),
            "broker_account_kind": kind_now,
            "spend_status": _safety.status_snapshot(kind_now)["spend_status"],
            "intentional_gateway_mode": _heal.intentional_mode(),
            "launch_action": "noop",
            "message": f"Already on a {target} IB account -- Gateway was not restarted.",
        }

    from ibkr.gateway_login_fill import snapshot_ibc_log

    origin_path, origin_size = snapshot_ibc_log()
    del origin_path
    launch = launch_or_focus_gateway(
        target,
        force_restart=(plan in ("replace_target", "start_ibc")),
    )
    from ibkr.gateway_trail import append_event as _trail

    _trail(
        actor="operator",
        event="click",
        requested=target,
        kind_before=kind_now,
        plan=plan,
        launch_action=str(launch.get("action") or ""),
        switched=False,
        note=str(launch.get("message") or "")[:240],
    )
    if launch.get("action") == "launched_ibc":
        from ibkr.ibc_log_harvest import record_recent_ibc_into_trail

        try:
            record_recent_ibc_into_trail(requested=target, origin_size=origin_size)
        except Exception:
            logger.warning("IBKR: IBC trail harvest failed", exc_info=True)
    if c._ib is not None and c._ib.isConnected():
        c._ib.disconnect()
    c._set_session(mode="disconnected", broker_account_kind="unknown")
    _session.set_disconnected()
    c.set_session_reason("connecting")
    c.wake_reconnect_loop()

    launch_ok = bool(launch.get("ok"))
    if launch_ok:
        _heal.record_connect_outcome("failed", reason="switch_ibc_started")
    else:
        _heal.record_connect_outcome("failed", reason="switch_ibc_failed")

    return {
        "ok": launch_ok,
        "error": None if launch_ok else launch.get("message") or "IBC launch failed",
        "requested_mode": target,
        "preferred_port": preferred_port,
        "persisted": persisted,
        "connected": False,
        "mode": "disconnected",
        "broker_account_kind": "unknown",
        "spend_status": _safety.status_snapshot("unknown")["spend_status"],
        "intentional_gateway_mode": _heal.intentional_mode(),
        "launch_action": launch.get("action"),
        "message": launch.get("message"),
        "plan": plan,
    }
