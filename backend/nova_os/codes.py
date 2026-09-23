"""
Nova OS stable vocabulary + policy metadata (Phase P1) — pure, no state.

Every code string is defined once in `constants.py` (centralized-constants
rule); this module only groups them into fast-membership frozensets, exposes
validators the event store uses to fail closed on unknown codes. (The loss
policy that capped the control mode went with the mode ladder, ADR 025.)

Nothing here reads the clock, touches the DB, or places an order.
"""
from __future__ import annotations

from constants import (
    NOVA_OS_ACTIONS,
    NOVA_OS_DECISIONS,
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
