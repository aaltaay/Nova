"""How one fill splits across the holders of a stock (ADR 063 decision 2, ADR 069 decision 1). Pure.

A fill first closes shares held the other way. **Between the books** (``closing``, ADR 063 unchanged): its
own book's first, then the other book's; Nova's own close takes from each book in proportion to what it
holds, in whole shares. **Inside a book**: the sender's own shares first, then the book's other holders' in
proportion; Nova's own close and a close of the whole bots' book take from every holder in proportion. What
is left opens for the holder that sent it -- Nova's own close never opens; if one did, it is yours, and a
close of the whole bots' book is the strategy bot's. Your close that reaches into the bots' book takes
Auto-entry's shares first: Auto-entry hands its exit to you (``YOURS_TO_SELL``).
"""
from __future__ import annotations

from constants_owners import HOLDER_AUTO_ENTRY, HOLDER_BOTS_BOOK, HOLDER_STRATEGY_BOT, HOLDER_YOU
from owners.whose import book_of

_EPS = 1e-6


def whole(*values: float) -> bool:
    return all(abs(v - round(v)) < _EPS for v in values)


def closing(holders: dict[str, float], size: float, first: str | None) -> dict[str, float]:
    """How many of a fill's ``size`` shares close each of two books' ``holders`` (shares held the other way)."""
    total = sum(holders.values())
    amount = min(size, total)
    if amount <= _EPS:
        return {}
    if first in holders:
        own = min(amount, holders[first])
        out = {first: own}
        other = next((side for side in holders if side != first), None)
        if other is not None and amount - own > _EPS:
            out[other] = amount - own
        return out
    if len(holders) == 1:
        return {next(iter(holders)): amount}
    # Nova's own close: in proportion to what each side holds, in whole shares where the shares are whole.
    big, small = sorted(holders, key=lambda side: -holders[side])
    part = amount * holders[big] / total
    if whole(amount, holders[big], holders[small]):
        part = float(round(part))
    part = min(part, holders[big])
    rest = amount - part
    if rest > holders[small]:
        rest = holders[small]
        part = amount - rest
    return {big: part, small: rest}


def proportional(holders: dict[str, float], amount: float) -> dict[str, float]:
    """``amount`` taken from ``holders`` in proportion to what each holds; whole shares when every number is
    whole (the largest remainders round up; a tie goes to the larger holder, then the name)."""
    total = sum(holders.values())
    amount = min(amount, total)
    if amount <= _EPS or total <= _EPS:
        return {}
    if len(holders) <= 2:
        return closing(holders, amount, None)  # ADR 063's own rounding for two
    raw = {h: amount * q / total for h, q in holders.items()}
    if not whole(amount, *holders.values()):
        return raw
    out = {h: float(int(v + _EPS)) for h, v in raw.items()}
    left = int(round(amount - sum(out.values())))
    for h in sorted(holders, key=lambda h: (-(raw[h] - out[h]), -holders[h], h))[:max(0, left)]:
        out[h] += 1.0
    return {h: n for h, n in out.items() if n > _EPS}


def split_fill(held: dict[str, float], size: float, buy: bool, sender: str | None) -> list[tuple[str, float, bool]]:
    """``[(holder, shares, closes)]`` for a fill of ``size`` shares (``buy`` or a sell) that ``sender`` sent,
    given each holder's signed shares in the stock (``held``): the closing parts first, then what it opens."""
    sign = 1.0 if buy else -1.0
    by_book: dict[str, dict[str, float]] = {}
    for holder, qty in held.items():
        if qty * sign < -_EPS:  # held the other way: this fill closes it
            by_book.setdefault(book_of(holder) or HOLDER_YOU, {})[holder] = abs(qty)
    parts: list[tuple[str, float, bool]] = []
    totals = {book: sum(inside.values()) for book, inside in by_book.items()}
    for book, amount in closing(totals, size, book_of(sender)).items():
        inside = by_book[book]
        first = sender if sender in inside else HOLDER_AUTO_ENTRY if sender == HOLDER_YOU else None
        if first in inside:
            own = min(amount, inside[first])
            parts.append((first, own, True))
            rest = {h: q for h, q in inside.items() if h != first}
            parts.extend((h, n, True) for h, n in proportional(rest, amount - own).items())
        else:
            parts.extend((h, n, True) for h, n in proportional(inside, amount).items())
    left = size - sum(n for _, n, _ in parts)
    if left > _EPS:
        opener = HOLDER_YOU if sender is None else HOLDER_STRATEGY_BOT if sender == HOLDER_BOTS_BOOK else sender
        parts.append((opener, left, False))
    return parts
