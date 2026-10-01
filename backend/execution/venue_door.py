"""What the execution door holds fixed about the venue for one send (#655).

``execute`` reads the desk's venue once, under its lock, and the order is checked against,
committed on and sent to that venue -- however the desk moves meanwhile. An order id is only
meaningful on the venue that issued it (practice ids restart at 1 per venue), so a caller
that knows the venue names it (``ExecutionCommand.expected_venue``).

One exception, the kill switch (spec D, #656): its sweep cancels every venue's working orders
whatever the desk shows, so a ``kill`` cancel names its ``target_venue`` and is sent there
(``resolve``). Nothing else may name one -- a place, a buy or any other source is refused -- and
Live only while IBKR, Live's broker, is connected.

Owner: this module (the rules; the lock and the send are ``execution.service``'s).
"""
from __future__ import annotations

from constants_sim import DESK_PRACTICE_VENUES, DESK_VENUE_LIVE, DESK_VENUES
from execution import inflight
from execution.models import ExecutionCommand

TARGET_REFUSED = "TARGET_VENUE_REFUSED"


def current() -> str:
    """The desk's venue now: ``live`` | ``paper`` | ``sim``."""
    from sim.mode import venue

    return venue()


def is_practice(venue: str | None) -> bool:
    """``venue`` is Paper or Sim; None reads the desk's venue now."""
    if venue is not None:
        return venue in DESK_PRACTICE_VENUES
    from sim.mode import is_practice_venue

    return is_practice_venue()


def ibkr_connected() -> bool:
    """IBKR, Live's broker, is enabled and connected."""
    from ibkr import client as _client

    return bool(_client.is_enabled() and _client.is_connected())


def target_refusal(cmd: ExecutionCommand) -> str | None:
    """Why ``cmd`` may not be sent to its ``target_venue``, or None."""
    target = cmd.target_venue
    if target not in DESK_VENUES:
        return f"unknown target venue {target!r} -- one of {', '.join(DESK_VENUES)}"
    if cmd.operation != "cancel" or cmd.source != "kill":
        return ("only the kill switch's cancels may name a venue other than the desk's -- every other "
                "order is sent on the desk's venue")
    if target == DESK_VENUE_LIVE and not ibkr_connected():
        return "Live's orders are IBKR's, and IBKR is not connected -- nothing was sent"
    return None


def resolve(cmd: ExecutionCommand) -> tuple[str, str | None]:
    """``(venue to send on, why it may not be)``: the target venue for a kill cancel, else the desk's."""
    if cmd.target_venue is None:
        return current(), None
    return str(cmd.target_venue), target_refusal(cmd)


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
