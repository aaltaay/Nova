"""The open Level 2 sockets per symbol, and which are Trader tabs' (ADR 043 decision 6).

``/ws/ibkr/depth/{symbol}`` registers each socket right after it counts as a
viewer (``ibkr.depth.ws_viewer_opened``) and drops it right before it stops
counting, with no await between, so the two counts move together. The Trader
tab's Level 2 opens its socket with ``?tab=1`` (and ``front=1`` while it is the
tab in front); any other Level 2 (the Account page's ladder, an older desk) has
no ``tab`` and keeps its line from ever being lent.

A line is lendable only while every one of its viewers is a Trader tab's socket:
a Record hold, auto-record or a loan counts as a viewer with no socket here, so
the counts differ and the line stays.

In memory, this process only: a restart starts empty, as the sockets do.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

_ids = itertools.count(1)
_open: dict[str, dict[int, "Socket"]] = {}
_front_seen: dict[str, float] = {}


@dataclass(frozen=True)
class Socket:
    tab: bool
    front: bool
    opened_at: float


def opened(symbol: str, *, tab: bool, front: bool, now: float) -> int:
    """A depth socket for ``symbol`` now counts as a viewer; its token for ``closed``."""
    sym = symbol.upper()
    token = next(_ids)
    _open.setdefault(sym, {})[token] = Socket(tab=bool(tab), front=bool(front), opened_at=float(now))
    if front:
        _front_seen[sym] = float(now)
    return token


def closed(symbol: str, token: int) -> None:
    sym = symbol.upper()
    rows = _open.get(sym)
    if rows is None:
        return
    rows.pop(token, None)
    if not rows:
        _open.pop(sym, None)


def seen_in_front(symbol: str, now: float) -> None:
    """A socket for ``symbol`` said it is the tab in front (before it counted as a viewer)."""
    _front_seen[symbol.upper()] = float(now)


def front_seen(symbol: str) -> float | None:
    return _front_seen.get(symbol.upper())


def count(symbol: str) -> int:
    return len(_open.get(symbol.upper()) or {})


def tab_count(symbol: str) -> int:
    return sum(1 for s in (_open.get(symbol.upper()) or {}).values() if s.tab)


def only_tabs(symbol: str, viewers: int) -> bool:
    """Every one of ``viewers`` is a Trader tab's socket (and there is at least one)."""
    tabs = tab_count(symbol)
    return tabs > 0 and tabs == count(symbol) == int(viewers)


def reset_for_tests() -> None:
    _open.clear()
    _front_seen.clear()
