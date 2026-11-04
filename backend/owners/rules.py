"""Paper's rules that keep the books apart (ADR 069 decisions 2-5). Pure over the ledger's holdings.

Asked at the execution door (``execution.practice_checks``) and again by the practice broker for callers that
bypass it, at placement and at the fill (``practice.order_rules.fill_refusal``). Each answers ``(reason, code)``
in words, or None. A ledger that keeps one pile (Sim) and Nova's own closes (no holder) are never refused here.

- **Your Sell is yours** (``OWNERS_NOT_YOURS``): a close sells or covers only its sender's own shares while
  someone else holds the stock the same way -- yours (and Auto-entry's, which hands you its exit) for you, a
  bot's own for a bot, the bots' book's for a close of the whole bots' book.
- **Never the other way** (``OWNERS_OTHER_SIDE``): nothing opens a side while anyone else holds the other one;
  one account is never long and short a stock (ADR 048).
- **Bots stay out of yours** (``OWNERS_BOT_STAYS_OUT``): no bot opens a stock you hold or have an order working
  on; a bot already in it the same way may add.
- **The bots' budget** (``OWNERS_BOTS_BUDGET``): a bot's entry may not take the bots' open positions and working
  entries past the budget (placement only: a working entry is already counted).
"""
from __future__ import annotations

from typing import Any

from constants_owners import (
    HOLDER_BOTS_BOOK,
    HOLDER_YOU,
    OWNER_BOTS,
    OWNERS_BOT_STAYS_OUT_CODE,
    OWNERS_BOTS_BUDGET_CODE,
    OWNERS_NOT_YOURS_CODE,
    OWNERS_OTHER_SIDE_CODE,
    YOURS_TO_SELL,
)
from owners.whose import book_of, holder_of, name_of

_EPS = 1e-9
_BUDGET_SLACK_USD = 0.005


def _held_by(holder: str, owners: Any, symbol: str) -> float:
    """What ``holder`` may close in ``symbol``: the bots' book's for its whole-book close; for you, yours and
    Auto-entry's (Auto-entry hands its exit to you, ``YOURS_TO_SELL``)."""
    if holder == HOLDER_BOTS_BOOK:
        return owners.book_qty(symbol, OWNER_BOTS)
    if holder == HOLDER_YOU:
        return sum(owners.qty_of(symbol, h) for h in YOURS_TO_SELL)
    return owners.qty_of(symbol, holder)


def _shares_of(holder: str, other: str) -> bool:
    """``other``'s shares are among what ``holder``'s order may close (its own, or the book it closes whole)."""
    if holder == HOLDER_BOTS_BOOK:
        return book_of(other) == OWNER_BOTS
    if holder == HOLDER_YOU:
        return other in YOURS_TO_SELL
    return other == holder


def _direction(side: str, short_entry: bool, own: float) -> int:
    """+1 opens or adds a long, -1 opens or adds a short, 0 closes the sender's own shares."""
    if short_entry:
        return -1
    if side == "BUY":
        return 0 if own < -_EPS else 1
    return 0  # a SELL that is not a short entry is risk-reducing (ADR 048)


def _whose(holder: str) -> str:
    return "yours" if holder == HOLDER_YOU else f"{name_of(holder)}'s".replace("The ", "the ", 1)


def _not_yours(holder: str, own: float, others: dict[str, float], symbol: str, cover: bool) -> tuple[str, str]:
    biggest = max(others, key=lambda h: abs(others[h]))
    rest = sum(abs(q) for q in others.values())
    if holder == HOLDER_YOU:
        held = f"You hold no {symbol}" if abs(own) < _EPS else f"You hold {abs(own):g} {symbol}"
        verb = "cover" if cover else "Sell"
        return (f"{held}; {'the' if abs(own) < _EPS else 'the other'} {rest:g} are {_whose(biggest)}. "
                f"Your {verb} closes only your shares.", OWNERS_NOT_YOURS_CODE)
    if holder == HOLDER_BOTS_BOOK:
        return (f"The bots hold {abs(own):g} {symbol}; the other {rest:g} are {_whose(biggest)}. "
                "Their close sells only the bots' shares.", OWNERS_NOT_YOURS_CODE)
    return (f"{name_of(holder)} holds {abs(own):g} {symbol}; the other {rest:g} are {_whose(biggest)}. "
            "Its close sells only its own shares.", OWNERS_NOT_YOURS_CODE)


def _your_working(ledger: Any, symbol: str) -> bool:
    return any(str(row.get("symbol") or "").upper() == symbol and holder_of(row) == HOLDER_YOU
               for row in ledger.working_orders())


def refusal(ledger: Any, *, symbol: str, side: str, qty: float, short_entry: bool, holder: str | None,
            price: float | None = None, budget_usd: float | None = None, used_usd: float = 0.0,
            at_fill: bool = False) -> tuple[str, str] | None:
    """``(reason, code)`` when Paper's books refuse this order; None to let it through."""
    owners = getattr(ledger, "owners", None)
    if owners is None or holder is None:
        return None
    sym, side_u, size = symbol.strip().upper(), side.strip().upper(), float(qty)
    own = _held_by(holder, owners, sym)
    others = {h: lot.qty for h, lot in owners.holders_of(sym).items() if not _shares_of(holder, h)}
    direction = _direction(side_u, short_entry, own)
    if direction == 0:
        cover = side_u == "BUY"
        mine = -own if cover else own
        same_way = {h: q for h, q in others.items() if (q < -_EPS if cover else q > _EPS)}
        if size > max(mine, 0.0) + _EPS and same_way:
            return _not_yours(holder, own, same_way, sym, cover)
        return None
    for other, q in sorted(others.items(), key=lambda kv: -abs(kv[1])):
        if q * direction < -_EPS:
            verb = "Buy" if direction > 0 else "Short"
            way = "long" if q > 0 else "short"
            who = "you are" if other == HOLDER_YOU else f"{name_of(other).replace('The ', 'the ', 1)} is"
            return (f"{verb} {sym} refused: {who} {way} {abs(q):g}. One account can't be long and short the same "
                    "stock.", OWNERS_OTHER_SIDE_CODE)
    if book_of(holder) != OWNER_BOTS:
        return None
    adds = own * direction > _EPS
    if not adds:
        if abs(owners.qty_of(sym, HOLDER_YOU)) > _EPS:
            return f"{name_of(holder)} skipped {sym}: you hold it.", OWNERS_BOT_STAYS_OUT_CODE
        if _your_working(ledger, sym):
            return f"{name_of(holder)} skipped {sym}: you have an order working on it.", OWNERS_BOT_STAYS_OUT_CODE
    if at_fill or budget_usd is None or price is None:
        return None
    new = size * float(price)
    if float(used_usd) + new > float(budget_usd) + _BUDGET_SLACK_USD:
        return (f"{name_of(holder)} skipped {sym}: the bots' ${float(budget_usd):,.0f} would be passed "
                f"(${float(used_usd):,.0f} held + ${new:,.0f}).", OWNERS_BOTS_BUDGET_CODE)
    return None


def for_order(ledger: Any, *, symbol: str, side: str, qty: float, short_entry: bool, source: str | None,
              origin: str | None, bot_id: str | None, price: float | None) -> tuple[str, str] | None:
    """``refusal`` for an order not yet placed, with the bots' budget read now (Paper's setting)."""
    from owners import budget
    from owners.whose import holder_of_order

    if getattr(ledger, "owners", None) is None:
        return None
    holder = holder_of_order(source, origin, bot_id)
    bots = book_of(holder) == OWNER_BOTS
    return refusal(ledger, symbol=symbol, side=side, qty=qty, short_entry=short_entry, holder=holder, price=price,
                   budget_usd=budget.bots_usd() if bots else None, used_usd=budget.used_usd(ledger) if bots else 0.0)


def at_fill(ledger: Any, row: dict[str, Any]) -> tuple[str, str] | None:
    """``refusal`` for a working order about to fill: who holds what may have changed since it was placed."""
    reason = refusal(ledger, symbol=str(row["symbol"]), side=str(row["side"]), qty=float(row["qty"]),
                     short_entry=bool(row.get("short_entry")), holder=holder_of(row), at_fill=True)
    return None if reason is None else (reason[0] + " This order was cancelled at its fill.", reason[1])
