"""What the daily loss limit counts: trades opened today, and nothing held before (ADR 056). Pure.

Per stock with fills today: the cash those fills moved (a buy pays, a sell receives), less their
commissions and fees, plus the shares still held at the account's own mark. A stock the account
already held when the day began (its shares now less today's net is not zero) never counts,
however it was traded today. An open position with no usable mark makes the whole figure
unknown: a stated unknown, never a guess. An unknown commission is counted as unknown in words
but the rest still counts -- a commission only ever adds to a loss.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Mapping

_EPS = 1e-6


@dataclass(frozen=True)
class Fill:
    symbol: str
    shares: float          # signed: + bought, - sold
    price: float
    cost: float | None     # commission and fees; None when the account has not said


@dataclass(frozen=True)
class Held:
    shares: float          # signed: + long, - short
    mark: float | None


@dataclass
class Count:
    pnl: float | None                      # today's trades' P&L, negative a loss; None when unknown
    unknown: str | None = None             # why ``pnl`` is None
    stocks: list[dict] = field(default_factory=list)   # [{symbol, pnl, shares}] counted today
    held_before: list[str] = field(default_factory=list)  # stocks held before today: never counted
    costs_unknown: int = 0                 # fills whose commission the account has not said

    @property
    def loss(self) -> float | None:
        """The loss as a positive number (0 for a gain); None when unknown."""
        return None if self.pnl is None else max(0.0, -self.pnl)

    def opened_today(self) -> list[dict]:
        """The stocks Auto sell may sell: counted today and still held."""
        return [s for s in self.stocks if abs(s["shares"]) > _EPS]


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def count(fills: Iterable[Fill], held: Mapping[str, Held]) -> Count:
    by_symbol: dict[str, list[Fill]] = {}
    for fill in fills:
        by_symbol.setdefault(fill.symbol.upper(), []).append(fill)
    out = Count(pnl=0.0)
    total = 0.0
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
        if abs(shares_now) > _EPS:
            mark = now.mark if now is not None else None
            if not _finite(mark) or mark <= 0:
                return Count(pnl=None, unknown=f"{symbol} has no price to mark its open shares",
                             held_before=out.held_before, costs_unknown=out.costs_unknown)
            cash += shares_now * mark
        total += cash
        out.stocks.append({"symbol": symbol, "pnl": round(cash, 2), "shares": shares_now})
    out.pnl = round(total, 2)
    return out
