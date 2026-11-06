"""The books on the wire: each position's holders and the account's two books (ADR 069 Data). Pure reads.

``position_owners`` is a position row's ``by_owner[]``: ``{owner, bot, qty, avg_cost, unrealized_pnl}`` per
holder with shares, each at its own cost. ``books`` is ``/api/practice/account``'s ``books``: yours and the
bots', each ``{day_pnl, realized_today, unrealized_pnl, fills_today, commissions_today}``, and the bots'
adds ``budget_usd``, ``budget_used_usd`` and ``by_bot`` (the same figures per bot). Both are None on a
ledger that keeps one pile (Sim).

The two books' day P&L add up to the account's: the bots' figure takes what rounding leaves, and on a day
whose start was written before ADR 069 (a rollover without each holder's P&L) any difference the marks at
that boundary made.
"""
from __future__ import annotations

from typing import Any

from constants_owners import HOLDER_YOU, OWNER_BOTS, OWNER_YOU, YOURS_TO_SELL
from owners.whose import book_of, bot_of

_FIELDS = ("day_pnl", "realized_today", "unrealized_pnl", "fills_today", "commissions_today")


def position_owners(ledger: Any, symbol: str, mark: float) -> list[dict[str, Any]]:
    owners = getattr(ledger, "owners", None)
    if owners is None:
        return []
    return [
        {"owner": book_of(holder), "bot": bot_of(holder), "qty": lot.qty, "avg_cost": round(lot.avg, 4),
         "unrealized_pnl": round((float(mark) - lot.avg) * lot.qty, 4)}
        for holder, lot in owners.holders_of(symbol).items()
    ]


def yours(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Position rows as the operator's own controls see them: the shares yours to sell -- yours, and
    Auto-entry's, which hands you its exit (``YOURS_TO_SELL``) -- at their cost, the account's in
    ``account_qty``; a stock only other bots hold is left out. Rows with no ``by_owner`` (Sim) pass unchanged."""
    out: list[dict[str, Any]] = []
    for row in rows:
        holders = row.get("by_owner")
        if holders is None:
            out.append(row)
            continue
        mine = [h for h in holders if (h.get("bot") or HOLDER_YOU) in YOURS_TO_SELL]
        qty = sum(float(h["qty"]) for h in mine)
        if not mine or abs(qty) < 1e-9:
            continue
        size = sum(abs(float(h["qty"])) for h in mine)
        avg = sum(abs(float(h["qty"])) * float(h["avg_cost"]) for h in mine) / size
        mark = float(row.get("market_price") or 0.0)
        out.append({**row, "qty": qty, "avg_cost": round(avg, 4), "account_qty": row["qty"],
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


def books(ledger: Any, *, account_day_pnl: float, budget_usd: int, used_usd: float) -> dict[str, Any] | None:
    owners = getattr(ledger, "owners", None)
    if owners is None:
        return None
    mark_of = ledger.mark_or_cost
    order = [*owners.fills, *(h for h in owners.realized if h not in owners.fills)]  # first-fill order
    bots = [h for h in order if book_of(h) == OWNER_BOTS]
    you = _figures(owners, [HOLDER_YOU], mark_of)
    theirs = _figures(owners, bots, mark_of)
    theirs["day_pnl"] = round(float(account_day_pnl) - you["day_pnl"], 2)
    theirs["budget_usd"] = int(budget_usd)
    theirs["budget_used_usd"] = round(float(used_usd), 2)
    theirs["by_bot"] = {bot: _figures(owners, [bot], mark_of) for bot in bots}
    return {OWNER_YOU: you, OWNER_BOTS: theirs}
