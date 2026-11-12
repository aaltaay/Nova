"""What a Level 2 or Time & Sales socket tells the operator's lane (ADR 071 decision 2).

The two socket routes call these and nothing else of the package. A lane fault never costs the operator a
line: each logs and lets the socket go ahead, as it did before there were lanes.

- ``opening`` before the socket asks for its line: a socket in front moves the lane to its stock;
- ``opened`` once the line is up: the lane holds it.

A replay desk off the live edge has no IBKR line to hold, so both do nothing there.
"""
from __future__ import annotations

import logging

from line_lanes import yours
from line_lanes.yours import DEPTH, TAPE

logger = logging.getLogger(__name__)

__all__ = ["DEPTH", "TAPE", "opened", "opening"]


def _live_desk() -> bool:
    from sim.mode import is_replay_desk

    return not is_replay_desk()


async def opening(symbol: str, *, front: bool) -> None:
    if not front:
        return
    try:
        if _live_desk():
            await yours.moving_to(symbol)
    except Exception:
        logger.exception("LANES: could not move your lane to %s -- its socket goes ahead", symbol)


def opened(symbol: str, kind: str, *, front: bool) -> None:
    if not front:
        return
    try:
        if _live_desk():
            yours.hold(symbol, kind)
    except Exception:
        logger.exception("LANES: could not hold %s's %s line for your lane", symbol, kind)
