"""The short check the execution door runs on a short entry, under its lock (ADR 048).

``execution.validate.check_account_and_position`` hands every place or bracket that carries
``short_entry`` here. The facts that could wait on something -- the borrow, IBKR's what-if, SSR,
halts -- were gathered before the lock (``short_sale.facts``); here the door reads the account
from memory (positions, equity, margin, the shorts in flight on this venue) and runs the rules
(``short_sale.check``). The first rule that fails refuses, with its numbers and its fix.

Live needs ``IBKR_SHORT_ENABLED`` before anything else (ADR 009), and is refused at once while
it is off. Paper and Sim need no Live key: they short on their own ledger (ADR 048 step 2).
"""
from __future__ import annotations

import logging
from typing import Any

from constants_shorts import SHORT_REPRICE
from execution import inflight
from execution.models import ExecutionCommand
from ibkr.errors import IbkrAccountError
from short_sale import check, margin, whatif
from short_sale.facts import Facts, gather

logger = logging.getLogger(__name__)

Refusal = tuple[str, str]   # (detail, reason_code)


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def entry_price(cmd: ExecutionCommand) -> float | None:
    """The short's limit: a place's ``limit_price`` (a LMT only), a bracket's ``entry_price``."""
    if cmd.operation == "bracket":
        return _num(cmd.entry_price)
    if (cmd.order_type or "").strip().upper() != "LMT":
        return None
    return _num(cmd.limit_price)


def order_qty(cmd: ExecutionCommand) -> float:
    return abs(float(cmd.qty if cmd.qty is not None else cmd.shares or 0))


def order_from(cmd: ExecutionCommand) -> check.Order:
    """The short as the rules read it: a place carries no stop, so it is refused for one."""
    bracket = cmd.operation == "bracket"
    return check.Order(
        symbol=cmd.normalized_symbol() or "", qty=order_qty(cmd), entry=entry_price(cmd),
        stop=_num(cmd.stop_price) if bracket else None, target=_num(cmd.target_price) if bracket else None,
        side_ok=bracket or (cmd.side or "").upper() == "SELL",
    )


def _venue(venue: str | None) -> str:
    if venue:
        return venue
    from sim.mode import venue as desk_venue

    return desk_venue()


def _flying(symbol: str, venue: str) -> tuple[float, tuple[tuple[float, float], ...], float]:
    """Shorts on the way on ``venue``: this stock's shares, those with their limits, and what the others' need.

    Each keeps its own limit: a short resting at $20 is never priced at a new $15 entry.
    """
    same, other = 0.0, 0.0
    priced: list[tuple[float, float]] = []
    for row in inflight.commitments(inflight.SHORT, venue):
        if row.symbol == symbol:
            same += row.qty
            if row.price is not None:
                priced.append((row.qty, row.price))
        elif row.price is not None:
            factor, _ = whatif.ratio(row.symbol, "short")
            other += margin.short_requirement(row.price, row.qty) * factor
    return same, tuple(priced), other


def read_account(symbol: str, venue: str) -> check.Account:
    """The account the short is judged against: the venue's own, read from memory."""
    same, same_at, other = _flying(symbol, venue)
    try:
        if venue in ("paper", "sim"):
            from practice.broker import for_venue

            broker = for_venue(venue)
            held = broker.ledger.held_qty(symbol)
            return check.Account(summary=broker.account_summary(), positions=broker.positions(),
                                 held_long=max(0.0, held), held_short=max(0.0, -held),
                                 flying_same=same, flying_other_maint=other, flying_same_at=same_at)
        from ibkr import account as _acct

        return check.Account(summary=_acct.get_account_summary(), positions=list(_acct.get_positions() or []),
                             held_long=float(_acct.long_qty(symbol)), held_short=float(_acct.short_qty(symbol)),
                             flying_same=same, flying_other_maint=other, flying_same_at=same_at)
    except IbkrAccountError as exc:
        logger.exception("short check: the account could not be read -- refusing the short of %s", symbol)
        return check.Account(summary=None, positions=[], held_long=None, held_short=None, error=str(exc),
                             flying_same=same, flying_other_maint=other, flying_same_at=same_at)


def verdicts(cmd: ExecutionCommand, *, facts: Facts | None = None, borrow: dict[str, Any] | None = None,
             venue: str | None = None) -> list[check.Verdict]:
    """Every rule's verdict for the short entry ``cmd`` on ``venue``."""
    from ibkr import safety as _safety

    where = _venue(venue)
    order = order_from(cmd)
    if facts is None or facts.venue != where or facts.symbol != order.symbol:
        facts = gather(order.symbol, where, borrow=borrow)
    return check.rules(order, facts, read_account(order.symbol, where),
                       live_key=_safety.short_enabled() if where == "live" else None,
                       live_proof=live_proof() if where == "live" else None)


def live_proof() -> tuple[bool, str]:
    """The Live short proof's ``(complete, what is missing)`` (ADR 048 step 6); unreadable is incomplete."""
    try:
        from short_proof import status

        return status()
    except Exception:
        logger.exception("short check: the Live short proof could not be read -- refusing the Live short")
        return False, "the proof could not be read (the engine log has the details)."


def refusal(cmd: ExecutionCommand, *, facts: Facts | None = None, borrow: dict[str, Any] | None = None,
            venue: str | None = None) -> Refusal | None:
    """``(detail, reason_code)`` when the short entry ``cmd`` may not go out; None to let it."""
    from ibkr import safety as _safety

    if _venue(venue) == "live" and not _safety.short_enabled():
        return "IBKR_SHORT_ENABLED is false — short entry locked", "SHORT_DISABLED"
    return check.first_refusal(verdicts(cmd, facts=facts, borrow=borrow, venue=venue))


def replace_refusal(cmd: ExecutionCommand, venue: str | None) -> Refusal | None:
    """``(detail, reason_code)`` when ``cmd`` would reprice a working short entry; None otherwise.

    A replace runs no short check, so a new price could skip the borrow, SSR, margin and cushion
    rules the entry passed at its own price. Nova never reprices one: cancel it and place it again.
    Paper and Sim know their short entries; Live's are the ones Nova's execution record sent as
    short entries (ADR 048 step 6) -- a record Nova cannot read refuses, never guesses.
    """
    from practice.broker import for_venue

    where = _venue(venue)
    if cmd.order_id is None:
        return None
    oid = int(cmd.order_id)
    if where == "live":
        from execution import store_orders

        try:
            row = store_orders.short_entries([oid]).get(oid)
        except Exception:
            logger.exception("short check: the execution record could not be read for order %s", oid)
            return (f"Nova's execution record could not be read (the engine log has the details), so it cannot "
                    f"tell whether order {oid} is a short entry: it was not repriced. Cancel it and place it again.",
                    SHORT_REPRICE)
        symbol = row.get("symbol") if row else None
    elif where in ("paper", "sim"):
        rows = for_venue(where).working_orders()     # the broker the replace is sent to
        found = next((r for r in rows if int(r.get("order_id") or 0) == oid), None)
        row, symbol = (found if found is not None and found.get("short_entry") else None), (found or {}).get("symbol")
    else:
        return None
    if row is None:
        return None
    return (f"Order {oid} is a short entry ({symbol}): Nova never reprices one in place, "
            "because a new price needs the short check again (borrow, SSR, margin and the 25% cushion). "
            "Cancel it and place it again.", SHORT_REPRICE)
