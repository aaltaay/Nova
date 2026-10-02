"""Whether the setup scanner follows a listed name, and why not (ADR 044). Reads memory only.

Listed names share HOD Momo's reserved block with Former Momo (``hod_momo_active.build_active_set``): the
hot list first, in list order, ``HOD_MOMO_FORMER_MOMO_MAX_SLOTS`` slots in all. The setup scanner follows
the active set, so a listed name past the block -- or one IBKR cannot stream -- is not followed, and every
reader says why instead of showing it as quietly unwatched.
"""
from __future__ import annotations

import logging

from constants_hod_momo import HOD_MOMO_FORMER_MOMO_MAX_SLOTS
from constants_hot_list import HOT_LIST_ACTIVE_L1_BLOCKED, HOT_LIST_ACTIVE_OVER_RESERVED

logger = logging.getLogger(__name__)

RESERVED_FULL = f"HOD Momo's {HOD_MOMO_FORMER_MOMO_MAX_SLOTS} reserved slots are full"
L1_BLOCKED = "IBKR could not open its L1 line; Nova asks for it again after a cooldown"
NEXT_PASS = "HOD Momo admitted it; the setup scanner picks it up at its next pass"
NOT_REBUILT = "HOD Momo's active set has not been rebuilt since it was listed; its next pass takes it"
SCANNER_UNREAD = "the setup scanner could not be read, so whether it follows this name is unknown"


def universe() -> set[str] | None:
    """The names the setup scanner follows now, or None when it cannot be read (unknown, never "none")."""
    try:
        from setup_scanner.engine import get_engine

        return set(get_engine().universe)
    except Exception:
        logger.warning("hot list: the setup scanner's universe could not be read", exc_info=True)
        return None


def reason_not_followed(sym: str) -> str:
    """Why a name the setup scanner does not follow is left out, from HOD Momo's last admission."""
    import hod_momo_active as active

    why = active.get_priority_reason(sym)
    if why == HOT_LIST_ACTIVE_OVER_RESERVED:
        return RESERVED_FULL
    if why == HOT_LIST_ACTIVE_L1_BLOCKED:
        return L1_BLOCKED
    if why is not None and sym in active.get_active_symbols():
        return NEXT_PASS
    return NOT_REBUILT


def status(sym: str, followed_now: set[str] | None) -> tuple[bool | None, str | None]:
    """``(followed, why_not_followed)`` for one listed name against the scanner's universe."""
    if followed_now is None:
        return None, SCANNER_UNREAD
    if sym in followed_now:
        return True, None
    return False, reason_not_followed(sym)


def listed_note(sym: str) -> str | None:
    """The setup view's note for a listed name it does not follow; None when the name is not listed."""
    from hot_list.store import is_listed

    if not is_listed(sym):
        return None
    return f"{sym} is on today's hot list, but no lane reads it: {reason_not_followed(sym)}"
