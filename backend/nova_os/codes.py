"""
Nova OS stable vocabulary + policy metadata (Phase P1) — pure, no state.

Every code string is defined once in `constants.py` (centralized-constants
rule); this module only groups them into fast-membership frozensets, exposes
validators the event store uses to fail closed on unknown codes, and encodes
the temporary loss policy as a pure function over a consecutive-loss count.

Nothing here reads the clock, touches the DB, or places an order.
"""
from __future__ import annotations

from constants import (
    NOVA_OS_ACTIONS,
    NOVA_OS_DECISIONS,
    NOVA_OS_LOSS_POLICY_DOWNGRADE_AFTER_LOSSES,
    NOVA_OS_LOSS_POLICY_HALT_AFTER_LOSSES,
    NOVA_OS_MODE_CONFIRM,
    NOVA_OS_MODES,
    NOVA_OS_POLICY_VERSION,
    NOVA_OS_REASON_CODES,
)

# Frozensets for O(1) validation. Tuples in constants.py preserve order (used by
# the UI / policy endpoint); these enforce membership.
DECISIONS = frozenset(NOVA_OS_DECISIONS)
MODES = frozenset(NOVA_OS_MODES)
ACTIONS = frozenset(NOVA_OS_ACTIONS)
REASON_CODES = frozenset(NOVA_OS_REASON_CODES)

# Autonomy ranking (least → most). Used only to guarantee the loss policy can
# never raise autonomy — it may lower it toward human confirmation, never above.
_MODE_RANK = {mode: rank for rank, mode in enumerate(NOVA_OS_MODES)}


def policy_version() -> str:
    """The current decision-policy version stamped onto every event."""
    return NOVA_OS_POLICY_VERSION


def is_valid_decision(value: str) -> bool:
    return value in DECISIONS


def is_valid_mode(value: str) -> bool:
    return value in MODES


def is_valid_action(value: str) -> bool:
    return value in ACTIONS


def is_valid_reason(value: str) -> bool:
    return value in REASON_CODES


def validate_reason_codes(reasons: list[str]) -> list[str]:
    """Return any reason codes not in the stable vocabulary. Empty list == all
    valid. Callers fail closed on a non-empty result rather than persisting an
    unrecognized code into the audit log."""
    return [r for r in reasons if r not in REASON_CODES]


def _cap_at_confirm(requested_mode: str) -> str:
    """Return the LOWER-autonomy of `requested_mode` and `confirm`. A session
    already in `signal` (never acts) stays there; an auto mode drops to
    `confirm`. The loss policy can only lower autonomy, never raise it."""
    req_rank = _MODE_RANK.get(requested_mode, _MODE_RANK[NOVA_OS_MODE_CONFIRM])
    confirm_rank = _MODE_RANK[NOVA_OS_MODE_CONFIRM]
    return requested_mode if req_rank <= confirm_rank else NOVA_OS_MODE_CONFIRM


def loss_policy_mode(losses_today: int, requested_mode: str) -> tuple[str, str | None]:
    """Apply the temporary P1 loss policy to a requested control mode.

    Graduated response to losing trades THIS SESSION (calendar-day count,
    since the last session reset — a win in between two losses does not
    reset this counter; only `risk.reset_day()` does):
      >= HALT_AFTER_LOSSES       → cap at `confirm`, flag LOSS_POLICY_HALT
      >= DOWNGRADE_AFTER_LOSSES  → cap at `confirm`, flag LOSS_POLICY_DOWNGRADE
      otherwise                  → requested_mode unchanged, no reason

    `losses_today` is `strategy.risk.RiskState.losses_today` — deliberately
    NOT `consecutive_losses` (which resets on any win). A trader who loses,
    wins, loses, wins, loses has had three losing trades today and should
    still be downgraded/halted by this policy even though no two losses were
    back-to-back.

    Returns (effective_mode, reason_code_or_None). This never *raises* the
    autonomy level — it only lowers it toward human confirmation, so a losing
    day can never silently escalate to auto execution (a `signal`-only
    session stays `signal`).

    The actual day-halt lives in the risk engine (risk.can_trade()); this
    function reports the *reason code* for the audit trail and the safest mode
    to fall back to, leaving order-blocking to that engine.
    """
    if losses_today >= NOVA_OS_LOSS_POLICY_HALT_AFTER_LOSSES:
        return _cap_at_confirm(requested_mode), "LOSS_POLICY_HALT"
    if losses_today >= NOVA_OS_LOSS_POLICY_DOWNGRADE_AFTER_LOSSES:
        return _cap_at_confirm(requested_mode), "LOSS_POLICY_DOWNGRADE"
    return requested_mode, None
