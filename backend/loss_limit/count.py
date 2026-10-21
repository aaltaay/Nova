"""What the daily loss limit counts: trades opened today, nothing held before, and whose (ADR 056, ADR 061). Pure.

Per stock with fills today: the cash those fills moved (a buy pays, a sell receives), less their
commissions and fees, plus the shares still held at the account's own mark. A stock the account
already held when the day began (its shares now less today's net is not zero) never counts,
however it was traded today. An open position with no usable mark makes the whole figure
unknown: a stated unknown, never a guess. An unknown commission is counted as unknown in words
but the rest still counts -- a commission only ever adds to a loss.

**Whose trade (ADR 061).** A trade belongs to the side whose order opened its shares. ``Fill.by``
is ``you`` or ``bots`` -- read from the order's own stamps by ``loss_limit.accounts`` -- or None for
one of Nova's own closes (KILL, the day cover, a margin call, the Account line's Auto sell). A
stock's fills are read in the order they filled. Each first closes shares held the other way: its
own side's first, then the other side's, while Nova's own close takes from each side in proportion
to what it holds. The cash a close moves, and its share of the commission, go to the side whose
shares it closed. What is left opens for the side that sent it (Nova's own close never opens; if
one did, it is yours -- it is not a bot's order). Each side's P&L is its cash plus its shares at
the mark, and the two always add up to the account's.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from constants_loss_limit import LOSS_LIMIT_LINE_ACCOUNT, LOSS_LIMIT_LINE_YOU, LOSS_LIMIT_SIDES

_EPS = 1e-6


@dataclass(frozen=True)
class Fill:
    symbol: str
    shares: float          # signed: + bought, - sold
    price: float
    cost: float | None     # commission and fees; None when the account has not said
    by: str | None = LOSS_LIMIT_LINE_YOU    # ``you`` | ``bots`` | None: one of Nova's own closes
    ts: float = 0.0        # when it filled: a stock's fills are read in this order


@dataclass(frozen=True)
class Held:
    shares: float          # signed: + long, - short
    mark: float | None


@dataclass
class Count:
    pnl: float | None                      # today's trades' P&L, negative a loss; None when unknown
    unknown: str | None = None             # why ``pnl`` is None
    # [{symbol, pnl, shares, by: {you: {pnl, shares}, bots: {pnl, shares}}}] counted today
    stocks: list[dict] = field(default_factory=list)
    held_before: list[str] = field(default_factory=list)  # stocks held before today: never counted
    costs_unknown: int = 0                 # fills whose commission the account has not said
    sides: dict[str, float] = field(default_factory=dict)  # {you, bots}: each side's P&L

    @property
    def loss(self) -> float | None:
        """The account's loss as a positive number (0 for a gain); None when unknown."""
        return self.loss_of(LOSS_LIMIT_LINE_ACCOUNT)

    def pnl_of(self, line: str) -> float | None:
        """``line``'s P&L: the account's, or one side's; None when unknown."""
        if self.pnl is None:
            return None
        return self.pnl if line == LOSS_LIMIT_LINE_ACCOUNT else float(self.sides.get(line, 0.0))

    def loss_of(self, line: str) -> float | None:
        pnl = self.pnl_of(line)
        return None if pnl is None else max(0.0, -pnl)

    def opened_today(self, line: str = LOSS_LIMIT_LINE_ACCOUNT) -> list[dict]:
        """What Auto sell may sell for ``line``, ``[{symbol, pnl, shares}]``: counted today and still held --
        every share for the Account line, only that side's for a side line."""
        out: list[dict] = []
        for stock in self.stocks:
            mine = stock if line == LOSS_LIMIT_LINE_ACCOUNT else (stock.get("by") or {}).get(line) or {}
            shares = float(mine.get("shares") or 0.0)
            if abs(shares) > _EPS:
                out.append({"symbol": stock["symbol"], "pnl": mine.get("pnl"), "shares": shares})
        return out


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _whole(*values: float) -> bool:
    return all(abs(v - round(v)) < _EPS for v in values)


def _closing(holders: dict[str, float], size: float, first: str | None) -> dict[str, float]:
    """How many of a fill's ``size`` shares close each side's ``holders`` (shares held the other way)."""
    total = sum(holders.values())
    closing = min(size, total)
    if closing <= _EPS:
        return {}
    if first in holders:
        own = min(closing, holders[first])
        out = {first: own}
        other = next((side for side in holders if side != first), None)
        if other is not None and closing - own > _EPS:
            out[other] = closing - own
        return out
    if len(holders) == 1:
        return {next(iter(holders)): closing}
    # Nova's own close: in proportion to what each side holds, in whole shares where the shares are whole.
    big, small = sorted(holders, key=lambda side: -holders[side])
    part = closing * holders[big] / total
    if _whole(closing, holders[big], holders[small]):
        part = float(round(part))
    part = min(part, holders[big])
    rest = closing - part
    if rest > holders[small]:
        rest = holders[small]
        part = closing - rest
    return {big: part, small: rest}


def _split(rows: list[Fill]) -> dict[str, dict[str, float]]:
    """``{side: {cash, shares}}`` in one stock today: whoever opened the shares owns the trade."""
    own = {side: {"cash": 0.0, "shares": 0.0} for side in LOSS_LIMIT_SIDES}
    for fill in sorted(rows, key=lambda f: f.ts):
        size = abs(fill.shares)
        if size <= _EPS:
            continue
        sign = 1.0 if fill.shares > 0 else -1.0
        holders = {side: abs(own[side]["shares"]) for side in LOSS_LIMIT_SIDES if own[side]["shares"] * sign < -_EPS}
        parts = _closing(holders, size, fill.by)
        left = size - sum(parts.values())
        if left > _EPS:
            opener = fill.by if fill.by in LOSS_LIMIT_SIDES else LOSS_LIMIT_LINE_YOU
            parts[opener] = parts.get(opener, 0.0) + left
        for side, shares in parts.items():
            own[side]["shares"] += sign * shares
            own[side]["cash"] -= sign * shares * fill.price
            if fill.cost is not None:
                own[side]["cash"] -= fill.cost * shares / size
    return own


def count(fills: Iterable[Fill], held: Mapping[str, Held]) -> Count:
    by_symbol: dict[str, list[Fill]] = {}
    for fill in fills:
        by_symbol.setdefault(fill.symbol.upper(), []).append(fill)
    out = Count(pnl=0.0)
    total = 0.0
    sides = {side: 0.0 for side in LOSS_LIMIT_SIDES}
    for symbol in sorted(by_symbol):
        rows = by_symbol[symbol]
        now = held.get(symbol)
        shares_now = float(now.shares) if now is not None else 0.0
        net_today = sum(f.shares for f in rows)
        if abs(shares_now - net_today) > _EPS:
            out.held_before.append(symbol)
            continue
        cash = 0.0
        for fill in rows:
            cash -= fill.shares * fill.price
            if fill.cost is None:
                out.costs_unknown += 1
            else:
                cash -= fill.cost
        mark = 0.0
        if abs(shares_now) > _EPS:
            mark = now.mark if now is not None else None
            if not _finite(mark) or mark <= 0:
                return Count(pnl=None, unknown=f"{symbol} has no price to mark its open shares",
                             held_before=out.held_before, costs_unknown=out.costs_unknown)
            cash += shares_now * mark
        total += cash
        by: dict[str, dict[str, float]] = {}
        for side, own in _split(rows).items():
            pnl = own["cash"] + own["shares"] * mark
            sides[side] += pnl
            shares = own["shares"] if abs(own["shares"]) > _EPS else 0.0
            by[side] = {"pnl": round(pnl, 2), "shares": round(shares, 6)}
        out.stocks.append({"symbol": symbol, "pnl": round(cash, 2), "shares": shares_now, "by": by})
    out.pnl = round(total, 2)
    out.sides = {side: round(pnl, 2) for side, pnl in sides.items()}
    return out
