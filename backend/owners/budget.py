"""What an AI trader holds against its budget (ADR 072 decision 7, ``traders.md``): its open shares at the mark plus
its working entries at their own price -- an order that opens or adds; a close never counts.

The budget itself is each trader's limit (``traders.limits``). ADR 069's one bots' budget (``owners-budget.json``)
is retired with the bots; its file is left where it is and no longer read.
"""
from __future__ import annotations

from typing import Any


def used_usd(ledger: Any, trader: str, *, exclude_order_id: int | None = None) -> float:
    """What ``trader`` holds now on ``ledger``: open shares at the mark plus working entries at their price -- all
    but ``exclude_order_id``'s, the entry being repriced or filled."""
    from owners.whose import book_of, holder_of

    owners = getattr(ledger, "owners", None)
    if owners is None:
        return 0.0
    used = 0.0
    for symbol, lots in owners.lots.items():
        for holder, lot in lots.items():
            if book_of(holder) == trader and abs(lot.qty) > 1e-9:
                used += abs(lot.qty) * float(ledger.mark_of(symbol, lot.avg) or lot.avg)
    for row in ledger.working_orders():
        if row.get("effect") != "opens" or book_of(holder_of(row)) != trader:
            continue
        if exclude_order_id is not None and int(row.get("order_id") or -1) == int(exclude_order_id):
            continue
        price = row.get("limit_price") or row.get("stop_price") or ledger.mark_of(str(row["symbol"]))
        used += float(row.get("remaining_qty") or row.get("qty") or 0) * float(price or 0)
    return used
