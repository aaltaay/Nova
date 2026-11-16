"""Which stock each lane is on, and what a change costs in IBKR lines (ADR 071 decisions 1, 3, 7).

Pure: no IBKR, no clock. ``put`` answers the new table and the ``Move`` -- the stocks whose lines end and
the stocks whose lines open. A stock two owners are on is one pair of lines, so it ends only when the last
owner leaves it, and opens only for the first.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

YOU = "you"
CLAUDE = "claude"
BOTS = "bots"
OWNERS = (YOU, CLAUDE, BOTS)


@dataclass(frozen=True)
class Lanes:
    """The stock each owner's lane is on; ``None`` for an empty lane."""

    you: str | None = None
    claude: str | None = None
    bots: str | None = None

    def on(self, owner: str) -> str | None:
        return getattr(self, _owner(owner))

    def stocks(self) -> tuple[str, ...]:
        """Every stock a lane is on, once each, sorted: the IBKR line pairs in use (three at most)."""
        return tuple(sorted({s for s in (self.you, self.claude, self.bots) if s}))

    def owners_of(self, symbol: str) -> tuple[str, ...]:
        """The owners whose lane is on ``symbol``, in ``OWNERS`` order."""
        sym = _symbol(symbol)
        return tuple(o for o in OWNERS if sym and getattr(self, o) == sym)


@dataclass(frozen=True)
class Move:
    """What a change costs: the stocks whose two lines end, and the stocks whose two lines open."""

    close: tuple[str, ...] = ()
    open: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.close or self.open)


def put(lanes: Lanes, owner: str, symbol: str | None) -> tuple[Lanes, Move]:
    """Put ``owner``'s lane on ``symbol`` (``None`` empties it): the new table and the lines that change."""
    after = replace(lanes, **{_owner(owner): _symbol(symbol)})
    before_stocks, after_stocks = set(lanes.stocks()), set(after.stocks())
    return after, Move(close=tuple(sorted(before_stocks - after_stocks)),
                       open=tuple(sorted(after_stocks - before_stocks)))


def _owner(owner: str) -> str:
    if owner not in OWNERS:
        raise ValueError(f"no such lane owner: {owner!r}")
    return owner


def _symbol(symbol: str | None) -> str | None:
    return (symbol or "").strip().upper() or None
