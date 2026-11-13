"""What a Level 2 or Time & Sales socket tells the lanes, and the sockets open now (ADR 071 decisions 2, 4).

The two socket routes call these and nothing else of the package:

- ``flags``: the socket's ``tab`` and ``front`` query flags (``?tab=1&front=1``: a desk Trader tab's, opened while it
  was the tab in front; the phone's Trade screen and other panes send ``front`` without ``tab``);
- ``opening`` before the socket asks for its line: a socket in front moves your lane to its stock. A lane fault never
  costs the operator a line: it is logged and the socket goes ahead (the gate then answers for its line);
- ``opened`` / ``closed`` right after the socket counts as a viewer and right before it stops: the sockets open per
  stock, read by the lanes' recording (``shown_by_socket``) and ``tape_heal`` (``count``, ``opened_in_front``);
- ``ends_line``: whether this socket closing may end its stock's line -- only a stock no lane is on (a Sim replay
  slot). A lane's line ends only when its lane leaves (``lanes.put``);
- ``line_down``: a Time & Sales socket found its line down, and ``tape_heal`` brings it back (#698).

A replay desk off the live edge has no IBKR line to hold: there ``opening`` does nothing. In memory, this process
only: a restart starts empty, as the sockets do.
"""
from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from typing import Any, Mapping

from line_lanes import lanes, yours

logger = logging.getLogger(__name__)

DEPTH = "depth"
TAPE = "tape"

_ids = itertools.count(1)
_open: dict[tuple[str, str], dict[int, "Socket"]] = {}


@dataclass(frozen=True)
class Socket:
    tab: bool
    front: bool


def reset_for_tests() -> None:
    _open.clear()


def flags(params: Mapping[str, Any]) -> tuple[bool, bool]:
    """``(tab, front)`` from a socket's query."""
    return str(params.get("tab") or "") == "1", str(params.get("front") or "") == "1"


def _live_desk() -> bool:
    from sim.mode import is_replay_desk

    return not is_replay_desk()


async def opening(symbol: str, *, front: bool) -> None:
    if not front:
        return
    try:
        if _live_desk():
            await yours.move_to(symbol)
    except Exception:
        logger.exception("LANES: could not move your lane to %s -- its socket goes ahead", symbol)


def ends_line(symbol: str) -> bool:
    """A socket closing ends its stock's line only when no lane is on it."""
    return not lanes.on_lane(symbol)


def opened(symbol: str, *, tab: bool, front: bool, kind: str = DEPTH) -> int:
    """A ``kind`` socket for ``symbol`` now counts as a viewer of its line; its token for ``closed``."""
    token = next(_ids)
    _open.setdefault((kind, symbol.upper()), {})[token] = Socket(tab=bool(tab), front=bool(front))
    return token


def closed(symbol: str, token: int | None, kind: str = DEPTH) -> None:
    if token is None:
        return
    key = (kind, symbol.upper())
    rows = _open.get(key)
    if rows is None:
        return
    rows.pop(token, None)
    if not rows:
        _open.pop(key, None)


def count(symbol: str, kind: str = DEPTH) -> int:
    return len(_open.get((kind, symbol.upper())) or {})


def opened_in_front(symbol: str, kind: str = DEPTH) -> bool:
    """A ``kind`` socket for ``symbol`` opened as the tab in front, or from a pane outside a Trader tab."""
    return any(s.front or not s.tab for s in (_open.get((kind, symbol.upper())) or {}).values())


def shown_by_socket(symbol: str) -> dict[str, bool]:
    """Sockets opened in front on ``symbol`` still open: ``{"tab": ..., "other": ...}`` -- a desk Trader tab's (which
    the focus sensor knows better), or another surface's (the phone, a pane outside a Trader tab)."""
    sym = symbol.upper()
    rows = [s for kind in (DEPTH, TAPE) for s in (_open.get((kind, sym)) or {}).values() if s.front]
    return {"tab": any(s.tab for s in rows), "other": any(not s.tab for s in rows)}


def line_down(symbol: str, *, silence: dict | None = None) -> None:
    """A Time & Sales socket found its line down: ``tape_heal`` brings it back (#698)."""
    try:
        from line_lanes import tape_heal

        tape_heal.line_down(symbol, silence=silence)
    except Exception:
        logger.exception("IBKR tape: could not start bringing %s's Time & Sales line back", symbol)
