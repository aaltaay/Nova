"""Your lane: on the last stock you opened in front, with no timer (ADR 071 decisions 2, 3).

A Level 2 or Time & Sales socket that says it is in front (``front=1``: the Trader tab in front, a pop-out's tab, the
Desk's Trader slot, the phone's Trade screen) puts your lane on its stock before it asks for its line
(``lanes.put``): the old stock's two lines end at once unless another lane is on it, and the new stock's are asked
for. Closing the pane, hiding the tab or the phone's page going to the background changes nothing: the lane holds
both lines until you open another stock in front.

Not persisted: a restart closes every socket, and the first one in front names the lane again.
"""
from __future__ import annotations

from line_lanes import lanes
from line_lanes.table import YOU


def stock() -> str | None:
    """The stock your lane is on, or None before you opened one."""
    return lanes.table().you


async def move_to(symbol: str) -> None:
    """A socket in front is opening ``symbol``: your lane goes there now (nothing when it is already there)."""
    sym = (symbol or "").strip().upper()
    if sym and sym != stock():
        await lanes.put(YOU, sym)
