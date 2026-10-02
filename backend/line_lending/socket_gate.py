"""What a Level 2 or Time & Sales socket meets while its line may be lent (ADR 043 decision 6).

The two socket routes (``routes.trading_depth_ws``, ``routes.trading_tape_ws``) call
these, and nothing else of the lending package. A lending fault never costs the
operator a line: each logs and lets the socket go ahead.

- ``gate`` at open: the lent frame when the line is lent and this socket is not the
  tab in front, else None (a socket from the tab in front recalls the loan first);
- ``lent_now`` after the socket's queue opened: a loan that began while it subscribed
  pushed its frame before the queue existed;
- ``opened`` / ``closed`` keep ``line_lending.sockets`` beside the line's viewer count.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from line_lending.sockets import DEPTH

logger = logging.getLogger(__name__)


def flags(query_params: Any) -> tuple[bool, bool]:
    """``(tab, front)`` from a socket's query string (``?tab=1&front=1``)."""
    return query_params.get("tab") == "1", query_params.get("front") == "1"


async def gate(symbol: str, *, front: bool) -> dict[str, Any] | None:
    try:
        from line_lending import loans

        return await loans.on_socket_open(symbol, front=front)
    except Exception:
        logger.exception("line lending: the gate failed for %s's socket -- it goes ahead", symbol)
        return None


def lent_now(symbol: str, *, front: bool) -> dict[str, Any] | None:
    if front:
        return None
    try:
        from line_lending import loans

        return loans.lent_frame(symbol)
    except Exception:
        logger.exception("line lending: could not read the loans for %s's socket", symbol)
        return None


def opened(symbol: str, *, tab: bool, front: bool, kind: str = DEPTH) -> int | None:
    try:
        from line_lending import sockets

        return sockets.opened(symbol, tab=tab, front=front, now=time.time(), kind=kind)
    except Exception:
        logger.exception("line lending: could not register %s's %s socket", symbol, kind)
        return None


def closed(symbol: str, token: int | None, kind: str = DEPTH) -> None:
    if token is None:
        return
    try:
        from line_lending import sockets

        sockets.closed(symbol, token, kind)
    except Exception:
        logger.exception("line lending: could not drop %s's %s socket", symbol, kind)
