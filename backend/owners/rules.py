"""The rules that keep the three traders' books apart on Paper and Sim (ADR 072 decisions 3-5, ``traders.md``).

Asked at the execution door (``execution.practice_checks``) and again by the practice broker for callers that
bypass it, at placement and at the fill (``practice.order_rules.fill_refusal``). Each answers ``(reason, code)`` in
words, or None. A ledger without books and Nova's own closes (no holder) are never refused here.

- **A trader's stock is its own** (``OWNERS_TRADERS_STOCK``): nothing opens or adds on a stock another trader holds
  or has an entry working on (``stock_of``), nor on a stock handed to you -- you close a handed position, never add
  to it, and the trader that handed it may not act there at all (its own resting exits still fill).
- **Not while it is On** (``OWNERS_TRADER_ON``): no order of yours on a stock Claude or the brain owns while its
  switch is On, unless the position there is handed to you.
- **The budget** (``OWNERS_BUDGET``): an AI trader's entry may not take its open shares and working entries past its
  budget (``traders.limits``) -- at placement, when repriced up (``budget_refusal``) and at its fill.
- **Your Sell is yours** (``OWNERS_NOT_YOURS``): a close sells or covers only its sender's own shares -- for you,
  yours plus handed shares -- while someone else holds the stock the same way.
- **Never the other way** (``OWNERS_OTHER_SIDE``): nothing opens a side while anyone else holds the other one; one
  account is never long and short a stock (ADR 048).

A stock an AI trader holds while its switch is Off reads as handed even without a mark (``traders.handed``): Off
always hands what it held, so that is only the moment between the two.
"""
from __future__ import annotations

from typing import Any

from constants_owners import (
    AI_TRADERS,
    HOLDER_BOTS_BOOK,
    HOLDER_YOU,
    OWNER_EARLIER_BOTS,
    OWNER_NAMES,
    OWNER_YOU,
    OWNERS,
    OWNERS_BUDGET_CODE,
    OWNERS_NOT_YOURS_CODE,
    OWNERS_OTHER_SIDE_CODE,
    OWNERS_TRADER_ON_CODE,
    OWNERS_TRADERS_STOCK_CODE,
)
from owners.whose import book_of, holder_of, name_of

_EPS = 1e-9
_BUDGET_SLACK_USD = 0.005


def _the(owner: str) -> str:
    """A book's name mid-sentence: "Claude", "the brain", "the earlier bots"."""
    name = OWNER_NAMES.get(owner, owner)
    return name if owner not in (OWNER_EARLIER_BOTS, "brain") else name[0].lower() + name[1:]


def _whose(owner: str) -> str:
    return "yours" if owner == OWNER_YOU else f"{_the(owner)}'s"


def _is_on(trader: str) -> bool:
    from traders import switches

    return switches.is_on(trader)


def stock_of(ledger: Any, symbol: str) -> str | None:
    """Whose stock ``symbol`` is: the trader holding the most shares in it, else the one with an entry working
    there; ``you`` for a retired bot's shares (handed to you); None when nobody's."""
    owners = getattr(ledger, "owners", None)
    if owners is None:
        return None
    sym = symbol.strip().upper()
    held = sorted(owners.holders_of(sym).items(), key=lambda kv: -abs(kv[1].qty))
    for holder, _ in held:
        if book_of(holder) in OWNERS:
            return book_of(holder)
    if held:
        return OWNER_YOU
    for row in ledger.working_orders():
        if str(row.get("symbol") or "").upper() == sym and row.get("effect") == "opens":
            owner = book_of(holder_of(row))
            if owner in OWNERS:
                return owner
    return None


def handed_from(ledger: Any, symbol: str) -> str | None:
    """The trader (or ``earlier_bots``) whose position in ``symbol`` is handed to you now, else None."""
    from traders import handed

    owners = getattr(ledger, "owners", None)
    if owners is None:
        return None
    sym = symbol.strip().upper()
    marked = handed.active(getattr(ledger, "venue", None), ledger).get(sym)
    if marked is not None:
        return marked
    for holder, _lot in sorted(owners.holders_of(sym).items(), key=lambda kv: -abs(kv[1].qty)):
        owner = book_of(holder)
        if owner == OWNER_EARLIER_BOTS or (owner in AI_TRADERS and not _is_on(owner)):
            return owner
    return None


def _handed_qty(owners: Any, symbol: str, giver: str | None) -> float:
    if giver is None:
        return 0.0
    return owners.book_qty(symbol, giver)


def _closable(holder: str, owners: Any, symbol: str, giver: str | None) -> float:
    """What ``holder``'s close may sell or cover: yours plus handed shares for you; every holder's but yours for a
    whole-book close; a trader's own shares unless it handed them."""
    if holder == HOLDER_YOU:
        return owners.qty_of(symbol, HOLDER_YOU) + _handed_qty(owners, symbol, giver)
    if holder == HOLDER_BOTS_BOOK:
        return sum(lot.qty for h, lot in owners.holders_of(symbol).items() if h != HOLDER_YOU)
    if book_of(holder) == giver:
        return 0.0
    return owners.qty_of(symbol, holder)


def closable(ledger: Any, symbol: str, holder: str) -> float | None:
    """``holder``'s signed shares a close of its may reach in ``symbol`` (yours plus handed shares for you); None on
    a ledger without books, where the account's position answers."""
    owners = getattr(ledger, "owners", None)
    if owners is None:
        return None
    sym = symbol.strip().upper()
    return _closable(holder, owners, sym, handed_from(ledger, sym))


def _closes_share_of(holder: str, other: str, giver: str | None) -> bool:
    """``other``'s shares are among what ``holder``'s close may reach."""
    if holder == HOLDER_YOU:
        return other == HOLDER_YOU or (giver is not None and book_of(other) == giver)
    if holder == HOLDER_BOTS_BOOK:
        return other != HOLDER_YOU
    return other == holder and book_of(holder) != giver


def _direction(side: str, short_entry: bool, own: float) -> int:
    """+1 opens or adds a long, -1 opens or adds a short, 0 closes the sender's own shares."""
    if short_entry:
        return -1
    if side == "BUY":
        return 0 if own < -_EPS else 1
    return 0  # a SELL that is not a short entry is risk-reducing (ADR 048)


def _not_yours(holder: str, own: float, others: dict[str, float], symbol: str, cover: bool) -> tuple[str, str]:
    biggest = book_of(max(others, key=lambda h: abs(others[h]))) or OWNER_YOU
    rest = sum(abs(q) for q in others.values())
    tail = f", and {_the(biggest)} is On" if biggest in AI_TRADERS and _is_on(biggest) else ""
    if holder == HOLDER_YOU:
        held = f"You hold no {symbol}" if abs(own) < _EPS else f"You hold {abs(own):g} {symbol}"
        verb = "cover" if cover else "Sell"
        return (f"{held}; {'the' if abs(own) < _EPS else 'the other'} {rest:g} are {_whose(biggest)}{tail}. "
                f"Your {verb} closes only your shares.", OWNERS_NOT_YOURS_CODE)
    return (f"{name_of(holder)} holds {abs(own):g} {symbol}; the other {rest:g} are {_whose(biggest)}. "
            "Its close sells only its own shares.", OWNERS_NOT_YOURS_CODE)


def _stock_refusal(me: str, holder: str, sym: str, owner: str | None, giver: str | None,
                   direction: int) -> tuple[str, str] | None:
    """``OWNERS_TRADER_ON`` and ``OWNERS_TRADERS_STOCK``: whose stock it is and who may act there."""
    if me in AI_TRADERS and giver == me:
        return (f"{name_of(holder)} skipped {sym}: it handed {sym} to you when it was switched off, so it is yours "
                "to close.", OWNERS_TRADERS_STOCK_CODE)
    if me == OWNER_YOU and owner in AI_TRADERS and giver != owner and _is_on(owner):
        return f"{sym} is {_whose(owner)}. Switch {_the(owner)} off to close it yourself.", OWNERS_TRADER_ON_CODE
    if direction == 0:
        return None
    if giver is not None:
        if me == OWNER_YOU:
            return (f"{sym} was handed to you by {_the(giver)}: you close it, never add to it.",
                    OWNERS_TRADERS_STOCK_CODE)
        return f"{name_of(holder)} skipped {sym}: it is handed to you.", OWNERS_TRADERS_STOCK_CODE
    if owner is not None and owner != me:
        if me == OWNER_YOU:
            return f"{sym} is {_whose(owner)}: nobody adds to another trader's stock.", OWNERS_TRADERS_STOCK_CODE
        return (f"{name_of(holder)} skipped {sym}: it is {_whose(owner)}, and nobody adds to another trader's "
                "stock.", OWNERS_TRADERS_STOCK_CODE)
    return None


def refusal(ledger: Any, *, symbol: str, side: str, qty: float, short_entry: bool, holder: str | None,
            price: float | None = None, budget_usd: float | None = None, used_usd: float = 0.0,
            at_fill: bool = False) -> tuple[str, str] | None:
    """``(reason, code)`` when the books refuse this order; None to let it through."""
    owners = getattr(ledger, "owners", None)
    if owners is None or holder is None:
        return None
    sym, side_u, size = symbol.strip().upper(), side.strip().upper(), float(qty)
    me = book_of(holder)
    giver = handed_from(ledger, sym)
    own = _closable(holder, owners, sym, giver)
    direction = -1 if short_entry else _direction(side_u, False, own)
    if holder != HOLDER_BOTS_BOOK:
        if at_fill and me in AI_TRADERS and giver == me and direction == 0:
            pass  # its own resting exit still fills on shares it handed (traders.md)
        elif why := _stock_refusal(me, holder, sym, stock_of(ledger, sym), giver, direction):
            return why
    others = {h: lot.qty for h, lot in owners.holders_of(sym).items() if not _closes_share_of(holder, h, giver)}
    if direction == 0:
        cover = side_u == "BUY"
        mine = -own if cover else own
        same_way = {h: q for h, q in others.items() if (q < -_EPS if cover else q > _EPS)}
        if size > max(mine, 0.0) + _EPS and same_way and not (at_fill and giver == me):
            return _not_yours(holder, own, same_way, sym, cover)
        return None
    for other, q in sorted(others.items(), key=lambda kv: -abs(kv[1])):
        if q * direction < -_EPS:
            verb = "Buy" if direction > 0 else "Short"
            way = "long" if q > 0 else "short"
            who = "you are" if other == HOLDER_YOU else f"{name_of(other).replace('The ', 'the ', 1)} is"
            return (f"{verb} {sym} refused: {who} {way} {abs(q):g}. One account can't be long and short the same "
                    "stock.", OWNERS_OTHER_SIDE_CODE)
    if me not in AI_TRADERS or at_fill or budget_usd is None or price is None:
        return None
    return _past_budget(holder, sym, size * float(price), float(used_usd), float(budget_usd))


def _past_budget(holder: str, symbol: str, new: float, used: float, budget_usd: float) -> tuple[str, str] | None:
    if used + new > budget_usd + _BUDGET_SLACK_USD:
        return (f"{name_of(holder)} skipped {symbol}: its ${budget_usd:,.0f} would be passed "
                f"(${used:,.0f} held + ${new:,.0f}).", OWNERS_BUDGET_CODE)
    return None


def _closes(row: dict[str, Any]) -> bool:
    """The row says it closes: a bracket's target or stop (its entry's exit, ``parent_id`` set), or any row placed
    as a close (``effect``). Read from the row, never from what is held now -- a short bracket's BUY stop waits
    while nothing is held yet, and it still only ever covers (ADR 048)."""
    return row.get("effect") == "closes" or row.get("parent_id") is not None or row.get("leg_role") in ("target", "stop")


def budget_refusal(ledger: Any, row: dict[str, Any], price: float) -> tuple[str, str] | None:
    """An AI trader's budget for its working entry at ``price`` -- a reprice, or its fill: its open shares and its
    other working entries, plus this one at ``price``. None for your orders, closes and a ledger without books."""
    from owners import budget
    from traders import limits

    owners = getattr(ledger, "owners", None)
    holder = holder_of(row)
    trader = book_of(holder)
    if owners is None or holder is None or trader not in AI_TRADERS or _closes(row):
        return None  # a close -- a bracket's exit, even one still waiting on its entry -- never spends a budget
    sym = str(row["symbol"]).strip().upper()
    if _direction(str(row["side"]).strip().upper(), bool(row.get("short_entry")), owners.qty_of(sym, holder)) == 0:
        return None
    qty = float(row.get("remaining_qty") or row.get("qty") or 0)
    used = budget.used_usd(ledger, trader, exclude_order_id=int(row["order_id"]))
    return _past_budget(holder, sym, qty * float(price), used, float(limits.budget_usd(trader)))


def for_order(ledger: Any, *, symbol: str, side: str, qty: float, short_entry: bool, source: str | None,
              origin: str | None, bot_id: str | None, price: float | None) -> tuple[str, str] | None:
    """``refusal`` for an order not yet placed, with an AI trader's budget read now (``traders.limits``)."""
    from owners import budget
    from owners.whose import holder_of_order
    from traders import limits

    if getattr(ledger, "owners", None) is None:
        return None
    holder = holder_of_order(source, origin, bot_id)
    trader = book_of(holder)
    ai = trader in AI_TRADERS
    return refusal(ledger, symbol=symbol, side=side, qty=qty, short_entry=short_entry, holder=holder, price=price,
                   budget_usd=limits.budget_usd(trader) if ai else None,
                   used_usd=budget.used_usd(ledger, trader) if ai else 0.0)


def at_fill(ledger: Any, row: dict[str, Any], price: float | None = None) -> tuple[str, str] | None:
    """``refusal`` for a working order about to fill at ``price``: who holds what may have changed since it was
    placed, and an AI trader's entry still has to fit its budget at the price it fills."""
    reason = refusal(ledger, symbol=str(row["symbol"]), side=str(row["side"]), qty=float(row["qty"]),
                     short_entry=bool(row.get("short_entry")), holder=holder_of(row), at_fill=True)
    if reason is None and price is not None:
        reason = budget_refusal(ledger, row, float(price))
    return None if reason is None else (reason[0] + " This order was cancelled at its fill.", reason[1])
