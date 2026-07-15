"""
Nova OS control-mode state (Phase P4).

In-memory only — ALWAYS starts at NOVA_OS_DEFAULT_MODE (`signal`) on process
start and is never written to disk. Loss policy may lower effective autonomy
toward `confirm` but never raises it. P4 allows raising only to `signal` and
`confirm`; `auto_paper` / `auto_live` stay rejected until later phases.
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
from nova_os import codes
from nova_os.events import KIND_SYSTEM, record_receipt
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
        _risk.get_state().consecutive_losses, _mode
    )
    return effective


def get_effective_mode_detail() -> tuple[str, str | None]:
    """(effective_mode, loss_policy_reason_or_None)."""
    return codes.loss_policy_mode(_risk.get_state().consecutive_losses, _mode)


def set_mode(requested: str) -> str:
    """Raise/drop to an allowed P4 mode. Returns the new requested mode.

    Raises ValueError (409-style) for unknown modes or auto_* in P4.
    """
    global _mode
    if requested not in NOVA_OS_MODES:
        raise ValueError(f"unknown control mode: {requested!r}")
    if requested == NOVA_OS_MODE_AUTO_LIVE:
        raise ValueError("P4: auto modes not enabled yet")
    if requested == NOVA_OS_MODE_AUTO_PAPER:
        raise ValueError("P4: auto_paper not enabled yet — use P5")
    if requested not in (NOVA_OS_MODE_SIGNAL, NOVA_OS_MODE_CONFIRM):
        raise ValueError(f"P4: mode {requested!r} not allowed")

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
    return _mode


def force_signal(reason: str) -> str:
    """Unconditionally drop to signal (kill / disarm). Always journals."""
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
    return _mode


def reset_for_tests() -> None:
    """Test helper — restore default without journaling."""
    global _mode
    _mode = NOVA_OS_DEFAULT_MODE
