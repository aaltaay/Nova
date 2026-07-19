"""
Nova OS control-mode state (Phase P5).

In-memory only — ALWAYS starts at NOVA_OS_DEFAULT_MODE (`signal`) on process
start and is never written to disk. Loss policy may lower effective autonomy
toward `confirm` but never raises it.

P5 allows `signal` | `confirm` | `auto_paper` (paper Gateway + spend + risk +
not holiday). `auto_live` stays rejected — no live money.
"""
from __future__ import annotations

import logging

from constants import (
    NOVA_OS_DEFAULT_MODE,
    NOVA_OS_MODE_AUTO_LIVE,
    NOVA_OS_MODE_AUTO_PAPER,
    NOVA_OS_MODE_CONFIRM,
    NOVA_OS_MODE_SIGNAL,
    NOVA_OS_MODES,
)
from ibkr import client as _ibkr_client
from ibkr import safety as _ibkr_safety
from nova_os import codes
from nova_os.events import KIND_SYSTEM, record_receipt
from nova_os.gates import is_nyse_holiday
from strategy import risk as _risk

logger = logging.getLogger(__name__)

# Never persisted. Restart → signal.
_mode: str = NOVA_OS_DEFAULT_MODE


def get_mode() -> str:
    """Requested mode (what the operator last set), ignoring loss-policy cap."""
    return _mode


def get_effective_mode() -> str:
    """Requested mode after applying the temporary loss-policy cap."""
    effective, _reason = codes.loss_policy_mode(
        _risk.get_state().losses_today, _mode
    )
    return effective


def get_effective_mode_detail() -> tuple[str, str | None]:
    """(effective_mode, loss_policy_reason_or_None)."""
    return codes.loss_policy_mode(_risk.get_state().losses_today, _mode)


def auto_paper_gate_status() -> tuple[bool, str]:
    """Non-raising gate check — (ok, reason). Shared by set_mode() (raises on
    mode-raise) and executor.place_from_ticket() (must re-check at EVERY
    placement, not only at the moment the operator raised the mode — the
    gateway can disconnect, spend gates can trip, or risk can halt in the
    seconds between set_mode() and the next signal)."""
    if not _ibkr_client.is_connected():
        return False, "auto_paper requires IBKR connected on paper Gateway"
    account_mode = _ibkr_client.account_mode()
    if account_mode != "paper":
        return False, f"auto_paper requires paper Gateway (current account_mode={account_mode!r})"
    kind = _ibkr_client.broker_account_kind()
    if kind != "paper":
        return False, (
            f"auto_paper requires paper broker accounts (DU/DF); got {kind!r}"
        )
    if not _ibkr_safety.orders_enabled():
        return False, "auto_paper requires IBKR_ORDERS_ENABLED=true"
    ok, reason = _ibkr_safety.assert_orders_allowed(
        client_enabled=_ibkr_client.is_enabled(),
        connected=True,
        account_mode=account_mode,
        broker_account_kind=kind,
    )
    if not ok:
        return False, reason or "auto_paper blocked by IBKR spend gates"
    can, halt_reason = _risk.can_trade()
    if not can:
        return False, halt_reason or "auto_paper blocked: risk cannot trade"
    if is_nyse_holiday():
        return False, "auto_paper blocked: NYSE holiday"
    return True, "OK"


def _assert_auto_paper_allowed() -> None:
    """Raise ValueError with a plain reason if auto_paper cannot be enabled."""
    ok, reason = auto_paper_gate_status()
    if not ok:
        raise ValueError(reason)


def _reject_staged_on_signal_drop(reason: str) -> None:
    """Confirm-mode staged tickets are a promise of "nothing executes without
    a human clicking Approve." That promise is voided the instant the mode
    drops to signal — a stale Approve click a moment later must not place an
    order the operator no longer has automation armed for. Reject rather than
    silently orphan."""
    from nova_os import staged_tickets as _staged_tickets

    rejected = _staged_tickets.reject_all(f"mode_reset:{reason}")
    if rejected:
        logger.warning(
            "Nova OS: mode dropped to signal (%s) — rejected %s staged ticket(s)",
            reason,
            len(rejected),
        )


def set_mode(requested: str) -> str:
    """Raise/drop to an allowed mode. Returns the new requested mode.

    Raises ValueError (409-style) for unknown modes, auto_live, a tripped kill
    switch, or failed auto_paper gates.
    """
    global _mode
    if requested not in NOVA_OS_MODES:
        raise ValueError(f"unknown control mode: {requested!r}")
    if requested == NOVA_OS_MODE_AUTO_LIVE:
        raise ValueError(
            "auto_live is not enabled — live money stays blocked (use auto_paper on paper Gateway)"
        )
    if requested in (NOVA_OS_MODE_CONFIRM, NOVA_OS_MODE_AUTO_PAPER):
        from strategy import executor as _executor

        if _executor.is_kill_switch_tripped():
            raise ValueError(
                "kill switch is tripped — call reset_kill_switch() before raising control mode"
            )
    if requested == NOVA_OS_MODE_AUTO_PAPER:
        _assert_auto_paper_allowed()
    elif requested not in (NOVA_OS_MODE_SIGNAL, NOVA_OS_MODE_CONFIRM):
        raise ValueError(f"mode {requested!r} not allowed")

    previous = _mode
    _mode = requested
    logger.warning("Nova OS control mode: %s → %s", previous, requested)
    record_receipt(
        kind=KIND_SYSTEM,
        mode=requested,
        payload={
            "event": "mode_change",
            "from": previous,
            "to": requested,
            "effective": get_effective_mode(),
        },
    )
    if requested == NOVA_OS_MODE_SIGNAL:
        _reject_staged_on_signal_drop("set_mode_signal")
    return _mode


def force_signal(reason: str) -> str:
    """Unconditionally drop to signal (kill / disarm / recovery). Always journals."""
    global _mode
    previous = _mode
    _mode = NOVA_OS_MODE_SIGNAL
    logger.warning("Nova OS force_signal (%s): %s → signal", reason, previous)
    record_receipt(
        kind=KIND_SYSTEM,
        mode=NOVA_OS_MODE_SIGNAL,
        payload={
            "event": "force_signal",
            "from": previous,
            "to": NOVA_OS_MODE_SIGNAL,
            "reason": reason,
        },
    )
    _reject_staged_on_signal_drop(reason)
    return _mode


def reset_for_tests() -> None:
    """Test helper — restore default without journaling."""
    global _mode
    _mode = NOVA_OS_DEFAULT_MODE
