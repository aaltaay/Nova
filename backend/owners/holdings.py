"""Each holder's shares, cost and P&L in one account (ADR 069 decision 1). Pure bookkeeping.

The practice ledger feeds every fill here with the holder that sent it (``owners.whose.holder_of``); the
fill splits across the stock's holders (``owners.split``) and each part is booked at its holder's own
average cost, never a blended one. A part's share of the commission and fees goes with its shares (the last
part takes what rounding leaves, so the parts add up to the fill). The holders' realized P&L adds up to the
account's, and their shares to the account's position.

A day's figures start from ``mark_day_start``: the ledger stamps each holder's P&L on its ``rollover`` event
when it writes one, at the same marks as the event's equity, so the books' day P&L adds up to the account's;
a rollover written before ADR 069 is read at the last fill prices.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from owners.split import split_fill
from owners.whose import book_of

_EPS = 1e-9

MarkFn = Callable[[str], float]


@dataclass
class Lot:
    qty: float = 0.0       # signed: + long, - short
    avg: float = 0.0


@dataclass
class Part:
    holder: str
    shares: float
    closes: bool
    realized: float        # net of its cost
    commission: float
    fees: float            # the regulatory pass-throughs


@dataclass
class Holdings:
    lots: dict[str, dict[str, Lot]] = field(default_factory=dict)        # symbol -> holder -> lot
    realized: dict[str, float] = field(default_factory=dict)             # holder -> realized, net of costs
    commission: dict[str, float] = field(default_factory=dict)
    fees: dict[str, float] = field(default_factory=dict)
    fills: dict[str, int] = field(default_factory=dict)
    day_start_pnl: dict[str, float] = field(default_factory=dict)        # holder -> P&L at the day's start
    day_start_realized: dict[str, float] = field(default_factory=dict)
    day_start_costs: dict[str, tuple[float, float]] = field(default_factory=dict)
    day_start_fills: dict[str, int] = field(default_factory=dict)
    last_parts: list[Part] = field(default_factory=list)

    # ------------------------------------------------------------------ fills
    def apply(self, symbol: str, side: str, qty: float, price: float, sender: str | None, *,
              total: float, commission: float, fees: float) -> float:
        """Book one fill; returns its realized P&L, net of its ``total`` cost (``commission`` plus ``fees``)."""
        sym = symbol.upper()
        lots = self.lots.setdefault(sym, {})
        buy = side.upper() == "BUY"
        held = {h: lot.qty for h, lot in lots.items() if abs(lot.qty) > _EPS}
        split = split_fill(held, float(qty), buy, sender)
        cost_total = float(total)
        parts: list[Part] = []
        given_comm = given_fees = 0.0
        for index, (holder, shares, closes) in enumerate(split):
            last = index == len(split) - 1
            comm = float(commission) - given_comm if last else float(commission) * shares / float(qty)
            reg = float(fees) - given_fees if last else float(fees) * shares / float(qty)
            given_comm, given_fees = given_comm + comm, given_fees + reg
            cost = cost_total if len(split) == 1 else comm + reg
            lot = lots.setdefault(holder, Lot())
            if closes:
                gain = (lot.avg - price) * shares if buy else (price - lot.avg) * shares
                realized = gain - cost
                lot.qty += shares if buy else -shares
                if abs(lot.qty) < _EPS:
                    lot.qty, lot.avg = 0.0, 0.0
            else:
                size = abs(lot.qty) + shares
                lot.avg = (lot.avg * abs(lot.qty) + shares * price) / size
                lot.qty += shares if buy else -shares
                realized = -cost
            self.realized[holder] = self.realized.get(holder, 0.0) + realized
            self.commission[holder] = self.commission.get(holder, 0.0) + comm
            self.fees[holder] = self.fees.get(holder, 0.0) + reg
            parts.append(Part(holder, shares, closes, realized, comm, reg))
        counted = sender if sender in {p.holder for p in parts} else max(parts, key=lambda p: p.shares).holder
        self.fills[counted] = self.fills.get(counted, 0) + 1
        self.last_parts = parts
        return sum(p.realized for p in parts) if len(parts) > 1 else parts[0].realized

    # ------------------------------------------------------------------ reads
    def position(self, symbol: str) -> tuple[float, float]:
        """``(shares, average cost)`` the account holds in ``symbol``: the holders' together."""
        held = [lot for lot in self.lots.get(symbol.upper(), {}).values() if abs(lot.qty) > _EPS]
        if not held:
            return 0.0, 0.0
        if len(held) == 1:
            return held[0].qty, held[0].avg
        qty = sum(lot.qty for lot in held)
        size = sum(abs(lot.qty) for lot in held)
        return qty, sum(abs(lot.qty) * lot.avg for lot in held) / size

    def holders_of(self, symbol: str) -> dict[str, Lot]:
        """Every holder with shares in ``symbol``."""
        return {h: lot for h, lot in self.lots.get(symbol.upper(), {}).items() if abs(lot.qty) > _EPS}

    def qty_of(self, symbol: str, holder: str) -> float:
        lot = self.lots.get(symbol.upper(), {}).get(holder)
        return lot.qty if lot is not None and abs(lot.qty) > _EPS else 0.0

    def book_qty(self, symbol: str, book: str) -> float:
        return sum(lot.qty for h, lot in self.holders_of(symbol).items() if book_of(h) == book)

    def unrealized(self, mark_of: MarkFn) -> dict[str, float]:
        """Each holder's open P&L at ``mark_of(symbol)``."""
        out: dict[str, float] = {}
        for sym, lots in self.lots.items():
            for holder, lot in lots.items():
                if abs(lot.qty) > _EPS:
                    out[holder] = out.get(holder, 0.0) + (mark_of(sym) - lot.avg) * lot.qty
        return out

    def holders(self) -> list[str]:
        """Every holder that ever filled, in first-fill order."""
        return list(self.fills)

    def pnl(self, mark_of: MarkFn) -> dict[str, float]:
        """Each holder's P&L since the account opened: realized plus open at ``mark_of``."""
        open_pnl = self.unrealized(mark_of)
        return {h: self.realized.get(h, 0.0) + open_pnl.get(h, 0.0) for h in {*self.realized, *open_pnl}}

    # -------------------------------------------------------------------- day
    def mark_day_start(self, stamped: dict[str, Any] | None, mark_of: MarkFn) -> None:
        """Start a day: each holder's P&L as the rollover stamped it, else at ``mark_of``."""
        if isinstance(stamped, dict):
            self.day_start_pnl = {str(h): float(v) for h, v in stamped.items()}
        else:
            self.day_start_pnl = self.pnl(mark_of)
        self.day_start_realized = dict(self.realized)
        self.day_start_costs = {h: (self.commission.get(h, 0.0), self.fees.get(h, 0.0)) for h in self.commission}
        self.day_start_fills = dict(self.fills)

    def today(self, holder: str, mark_of: MarkFn) -> dict[str, float]:
        """``holder``'s day so far: ``{day_pnl, realized_today, fills_today, commissions_today}``."""
        now = self.pnl(mark_of).get(holder, 0.0)
        comm0, fees0 = self.day_start_costs.get(holder, (0.0, 0.0))
        return {
            "day_pnl": now - self.day_start_pnl.get(holder, 0.0),
            "realized_today": self.realized.get(holder, 0.0) - self.day_start_realized.get(holder, 0.0),
            "fills_today": self.fills.get(holder, 0) - self.day_start_fills.get(holder, 0),
            "commissions_today": (self.commission.get(holder, 0.0) - comm0) + (self.fees.get(holder, 0.0) - fees0),
        }
