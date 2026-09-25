"""The ticket's Flatten: close what is held and not already being closed (QA R32, R42).

``intent: "flatten"`` on ``POST /api/ibkr/order`` -- the Trader rail's Flatten,
the quick-bar Flatten and the ``exit_pos`` / ``cancel_and_exit`` Nova Actions
-- is sent as source ``flatten``: a protective source, never clamped by the
one-share test gate and placeable while disarmed. Protective sources skip the
manual SELL's OVERSELL check, because KILL and the account flatten cancel every
working order first and must still get flat while those cancels settle. The
ticket's Flatten cancels nothing, so this check holds it instead, inside the
execution lock (``execution.validate.check_account_and_position``): its size
may not exceed the venue's position less the closing orders already working
there or sent and not yet listed. Two Flatten clicks, or a Flatten over a
resting exit, can then never both send and both fill into a short (QA R42,
2026-09-22 -- the second of two flattens was accepted while the first rested,
and the Sim account ended short 2 GRML).

The venue's open orders are the truth for what can still fill: a verified
cancel has already left the list (``ibkr.cancel_verify``), and an in-flight
commitment whose order id the venue no longer lists is stale, not working.

A bracket's exits (#606) are one close, not two: its take-profit and stop-loss
share a one-cancels-other group, so at most one of them fills and the group
counts once. An exit still waiting on its entry -- the entry is itself working
-- closes nothing held yet (it sells what the entry has not bought) and counts
nothing. Both read the rows' ``oca_group`` / ``parent_id``, which only the
practice venues fill in today (Live rows carry neither, so Live is unchanged).
"""
from __future__ import annotations

from typing import Any

from execution import inflight
from execution.models import ExecutionCommand
from ibkr.errors import IbkrAccountError

REASON_CODE = "FLATTEN_NOT_A_CLOSE"
_EPS = 1e-9


def _qty(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def held_qty(symbol: str) -> float:
    """Signed position in ``symbol`` from the venue's own positions (raises ``IbkrAccountError``)."""
    from ibkr import account as _account

    return sum(
        _qty(row.get("qty")) for row in _account.get_positions() or []
        if str(row.get("symbol") or "").strip().upper() == symbol
    )


def closing_committed(symbol: str, side: str) -> tuple[float, list[int]]:
    """Shares of ``symbol`` already working or sent on the closing ``side``, and those order ids.

    Raises ``IbkrAccountError`` when the venue's open orders cannot be read --
    a failed read is never "nothing working".
    """
    from ibkr import orders as _orders

    committed = 0.0
    ids: list[int] = []
    groups: dict[Any, float] = {}  # one-cancels-other group -> the most any one of its orders closes
    rows = _orders.open_orders()
    working = {int(row["order_id"]) for row in rows if row.get("order_id") is not None}
    for row in rows:
        if str(row.get("symbol") or "").strip().upper() != symbol:
            continue
        if str(row.get("side") or "").strip().upper() != side:
            continue
        remaining = row.get("remaining_qty")
        open_qty = (
            _qty(remaining) if remaining is not None
            else _qty(row.get("qty")) - _qty(row.get("filled_qty"))
        )
        parent = row.get("parent_id")
        if open_qty <= _EPS or (parent is not None and int(parent) in working):
            continue  # nothing open, or an exit waiting on an entry that is still working
        group = row.get("oca_group") or (("parent", int(parent)) if parent is not None else None)
        if group is None:
            committed += open_qty
        else:
            groups[group] = max(groups.get(group, 0.0), open_qty)
        if row.get("order_id") is not None:
            ids.append(int(row["order_id"]))
    committed += sum(groups.values())
    # Committed under the execution lock but not yet an order: counted until it is one.
    for row in inflight.snapshot():
        if row["symbol"] == symbol and row["side"] == side and row["order_id"] is None:
            committed += _qty(row["qty"])
    return committed, ids


def refusal(cmd: ExecutionCommand) -> str | None:
    """Why this flatten is not a close of the position still open to close, or None when it is."""
    if cmd.operation != "place" or cmd.short_entry:
        return "A flatten closes a position; it cannot open one or carry legs"
    symbol = cmd.normalized_symbol() or ""
    side = (cmd.side or "").strip().upper()
    try:
        held = held_qty(symbol)
        if abs(held) < _EPS:
            return f"No open {symbol} position to flatten"
        closing = "SELL" if held > 0 else "BUY"
        if side != closing:
            return f"A {side} does not close the {symbol} position ({held:g})"
        committed, ids = closing_committed(symbol, closing)
    except IbkrAccountError as exc:
        return f"Positions or working orders unavailable ({exc}) -- cannot confirm the close"
    qty = _qty(cmd.qty)
    available = abs(held) - committed
    if qty <= available + _EPS:
        return None
    if committed <= _EPS:
        return f"Flatten size {qty:g} exceeds the {symbol} position ({abs(held):g})"
    orders = ", ".join(f"#{order_id}" for order_id in ids) or "being sent"
    if available <= _EPS:
        return (
            f"{symbol} is already being closed: {committed:g} shares working ({orders}) "
            "-- cancel that order first, or use KILL"
        )
    return (
        f"Flatten size {qty:g} exceeds the {available:g} {symbol} shares not already "
        f"being closed ({committed:g} working: {orders})"
    )
