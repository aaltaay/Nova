"""The brain's lane: on the one stock the brain names, and empty until it names one (ADR 072 decision 10).

Lane 3 is the brain's always, whether its switch is On or Off. Only ``POST /api/brain/watch`` moves it
(``brain.routes``); there is no rate limit and no minimum hold. Not persisted: a restart empties the lane and the
brain names its stock again.
"""
from __future__ import annotations

from line_lanes import lanes
from line_lanes.table import BRAIN

_WHY_MAX = 140
_why: str | None = None


def stock() -> str | None:
    """The stock the brain's lane is on, or None."""
    return lanes.table().brain


def why() -> str | None:
    """The brain's own words for naming its stock; None with an empty lane."""
    return _why if stock() else None


async def watch(symbol: str | None, reason: str | None = None) -> str | None:
    """Put the brain's lane on ``symbol`` (None empties it); the stock it is on afterwards."""
    global _why
    sym = (symbol or "").strip().upper() or None
    await lanes.put(BRAIN, sym)
    _why = ((reason or "").strip()[:_WHY_MAX] or None) if sym else None
    return stock()


def reset_for_tests() -> None:
    global _why
    _why = None
