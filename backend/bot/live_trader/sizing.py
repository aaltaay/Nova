"""How much of their position a host's change is, and what the bot's copy follows of it (ADR 055, "Their size"). Pure.

The bar shows a host's average, never their shares. A buy pulls the average toward the price it paid: from ``A`` to
``A'`` with the market at ``P``, they added ``|A - A'| / |A' - P|`` of what they held. A partial sale their platform
folds into the average (each sale's profit lowers it) moves it away from the market by the same rule: they sold
``|A - A'| / |P - A'|`` of what they held. The bot keeps a **target** -- the shares it would hold had it copied every
change exactly -- and sends an order only once the gap to it is worth the host's lot (``lot_usd``), so a host who
scales in pieces of a few shares is followed in whole lots (operator, 2026-10-22: "Their size, $500 lots").
Shapes: architecture/schema/bot.md ("The Live Trader bot").
"""
from __future__ import annotations

from typing import Any

from bot.live_trader.constants_live_trader import LT_SIZE_SHARE_MAX

EPS = 1e-9


def change_share(prev: float | None, new: float, market: float | None) -> float | None:
    """The share of their position a change of their average from ``prev`` to ``new`` added or sold, with the
    market at ``market``, capped at ``LT_SIZE_SHARE_MAX``; None when the numbers say nothing (no average before, no
    market)."""
    if not prev or prev <= 0 or not market or market <= 0:
        return None
    moved, gap = abs(prev - new), abs(new - market)
    if gap <= EPS:
        return LT_SIZE_SHARE_MAX if moved > EPS else 0.0     # their average moved onto the market: the most
    return min(moved / gap, LT_SIZE_SHARE_MAX)


def grown(target: float, share: float) -> float:
    """The target after an add of ``share`` of their position."""
    return target * (1.0 + share)


def shrunk(target: float, share: float) -> float:
    """The target after a sale of ``share`` of their position (all of it at most)."""
    return target * (1.0 - min(share, 1.0))


def lot_shares(gap: float, price: float, lot_usd: float) -> int:
    """The whole shares a gap of ``gap`` shares sends at ``price``: the gap rounded, or 0 while it is worth less
    than ``lot_usd`` (the change waits until it adds up)."""
    qty = int(round(gap))
    if qty <= 0 or price <= 0:
        return 0
    return qty if qty * price >= lot_usd - EPS else 0


def target_for(rs: dict[str, Any], index: int, held: float) -> float:
    """The target before group ``index`` of a row's changes: ``held`` the first time, then what the last change
    left. A group judged again (a short's add waiting on its borrow read) starts from the same target, never grows
    it twice."""
    if rs.get("target_at") == index and rs.get("target_before") is not None:
        return float(rs["target_before"])
    base = rs.get("target")
    return float(held if base is None else base)


def keep(rs: dict[str, Any], index: int, before: float, after: float) -> None:
    """Remember the target group ``index`` left (memory, on the row's snapshot: a restart starts from what the bot
    holds)."""
    rs.update(target_before=before, target=after, target_at=index)
