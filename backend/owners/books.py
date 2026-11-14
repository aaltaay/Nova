"""The books on the wire: each position's holders and the account's four books (ADR 072, ``traders.md``). Pure reads.

``position_owners`` is a position row's ``by_owner[]``: ``{owner, bot, qty, avg_cost, unrealized_pnl, handed}`` per
holder with shares, each at its own cost; ``handed`` is true on the shares handed to you (a switched-off trader's, or
Earlier bots'). ``books`` is ``/api/practice/account``'s ``books``: ``you``, ``claude``, ``brain`` and
``earlier_bots``, each ``{day_pnl, realized_today, unrealized_pnl, fills_today, commissions_today}``; Claude and the
brain add ``budget_usd`` and ``budget_used_usd`` (``traders.limits``), Earlier bots ``by_bot`` (the same figures per
retired bot). Both are None on a ledger without books.

The books' day P&L add up to the account's: Earlier bots' figure takes what rounding leaves, and on a day whose start
was written before ADR 069 (a rollover without each holder's P&L) any difference the marks at that boundary made.
"""
from __future__ import annotations

from typing import Any

from constants_owners import AI_TRADERS, BOOKS, HOLDER_YOU, OWNER_EARLIER_BOTS, OWNER_YOU
from owners.whose import book_of, bot_of

_FIELDS = ("day_pnl", "realized_today", "unrealized_pnl", "fills_today", "commissions_today")


def position_owners(ledger: Any, symbol: str, mark: float) -> list[dict[str, Any]]:
    owners = getattr(ledger, "owners", None)
    if owners is None:
        return []
    from owners.rules import handed_from

    giver = handed_from(ledger, symbol)
    return [
        {"owner": book_of(holder), "bot": bot_of(holder), "qty": lot.qty, "avg_cost": round(lot.avg, 4),
         "unrealized_pnl": round((float(mark) - lot.avg) * lot.qty, 4),
         "handed": giver is not None and book_of(holder) == giver}
        for holder, lot in owners.holders_of(symbol).items()
    ]


def yours(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Position rows as the operator's own controls see them: the shares yours to close -- yours, and those handed
    to you -- at their cost, the handed ones in ``handed_qty`` (from ``handed_from``) and the account's in
    ``account_qty``; a stock only another trader holds is left out. Rows with no ``by_owner`` pass unchanged."""
    out: list[dict[str, Any]] = []
    for row in rows:
        holders = row.get("by_owner")
        if holders is None:
            out.append(row)
            continue
        mine = [h for h in holders if h.get("owner") == HOLDER_YOU or h.get("handed")]
        qty = sum(float(h["qty"]) for h in mine)
        if not mine or abs(qty) < 1e-9:
            continue
        handed = [h for h in mine if h.get("handed")]
        size = sum(abs(float(h["qty"])) for h in mine)
        avg = sum(abs(float(h["qty"])) * float(h["avg_cost"]) for h in mine) / size
        mark = float(row.get("market_price") or 0.0)
        out.append({**row, "qty": qty, "avg_cost": round(avg, 4), "account_qty": row["qty"],
                    "handed_qty": sum(float(h["qty"]) for h in handed),
                    "handed_from": handed[0]["owner"] if handed else None,
                    "market_value": round(qty * mark, 4),
                    "unrealized_pnl": round(sum(float(h["unrealized_pnl"]) for h in mine), 4)})
    return out


def _figures(owners: Any, holders: list[str], mark_of: Any) -> dict[str, Any]:
    open_pnl = owners.unrealized(mark_of)
    out = {key: 0.0 for key in _FIELDS}
    out["fills_today"] = 0
    for holder in holders:
        today = owners.today(holder, mark_of)
        for key in ("day_pnl", "realized_today", "commissions_today"):
            out[key] += today[key]
        out["fills_today"] += int(today["fills_today"])
        out["unrealized_pnl"] += open_pnl.get(holder, 0.0)
    return {key: (round(value, 2) if key != "fills_today" else value) for key, value in out.items()}


def books(ledger: Any, *, account_day_pnl: float) -> dict[str, Any] | None:
    owners = getattr(ledger, "owners", None)
    if owners is None:
        return None
    from owners import budget
    from traders import limits

    mark_of = ledger.mark_or_cost
    order = [*owners.fills, *(h for h in owners.realized if h not in owners.fills)]  # first-fill order
    held = {*order, *(h for lots in owners.lots.values() for h in lots)}
    by_book = {book: [h for h in [*order, *sorted(held - set(order))] if book_of(h) == book] for book in BOOKS}
    out = {book: _figures(owners, by_book[book], mark_of) for book in BOOKS}
    out[OWNER_EARLIER_BOTS]["day_pnl"] = round(
        float(account_day_pnl) - sum(out[b]["day_pnl"] for b in BOOKS if b != OWNER_EARLIER_BOTS), 2)
    for trader in AI_TRADERS:
        out[trader]["budget_usd"] = int(limits.budget_usd(trader))
        out[trader]["budget_used_usd"] = round(budget.used_usd(ledger, trader), 2)
    out[OWNER_EARLIER_BOTS]["by_bot"] = {bot: _figures(owners, [bot], mark_of) for bot in by_book[OWNER_EARLIER_BOTS]}
    return {OWNER_YOU: out[OWNER_YOU], **{b: out[b] for b in BOOKS if b != OWNER_YOU}}
