"""What the execution door holds fixed about the venue for one send (#655).

``execute`` reads the desk's venue once, under its lock, and the order is checked against,
committed on and sent to that venue -- however the desk moves meanwhile. An order id is only
meaningful on the venue that issued it (practice ids restart at 1 per venue), so a caller
that knows the venue names it (``ExecutionCommand.expected_venue``).

Owner: this module (the rules; the lock and the send are ``execution.service``'s).
"""
from __future__ import annotations

from execution import inflight
from execution.models import ExecutionCommand


def current() -> str:
    """The desk's venue now: ``live`` | ``paper`` | ``sim``."""
    from sim.mode import venue

    return venue()


def wrong_venue(cmd: ExecutionCommand, send_venue: str) -> str | None:
    """Why the desk is not where the caller meant, or None."""
    if cmd.expected_venue and cmd.expected_venue != send_venue:
        return (f"the desk is on {send_venue}, not {cmd.expected_venue} -- an order id is only "
                "meaningful on the venue that issued it")
    return None


def moved(send_venue: str) -> str | None:
    """Why the order was not sent when the desk moved while it was checked, or None."""
    now = current()
    if now != send_venue:
        return (f"the desk moved from {send_venue} to {now} while the order was checked -- "
                "it was not sent; place it again")
    return None


def commit_position(cmd: ExecutionCommand, execution_id: str, symbol: str | None, venue: str | None = None) -> None:
    """Hold the position this send will consume until the order resolves.

    Short-opening SELLs are skipped — they add exposure instead of spending a
    long, and holding one would refuse a legitimate exit in the same symbol.
    """
    if cmd.operation != "place" or not symbol:
        return
    if (cmd.side or "").upper() == "SELL" and getattr(cmd, "short_entry", False):
        return
    inflight.commit(execution_id, symbol=symbol, side=cmd.side, qty=cmd.qty, venue=venue)
