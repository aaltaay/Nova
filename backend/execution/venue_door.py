"""What the execution door holds fixed about the venue for one send (#655).

``execute`` reads the desk's venue once, under its lock, and the order is checked against,
committed on and sent to that venue -- however the desk moves meanwhile. An order id is only
meaningful on the venue that issued it (practice ids restart at 1 per venue), so a caller
that knows the venue names it (``ExecutionCommand.expected_venue``).

Two exceptions. The kill switch (spec D, #656): its sweep cancels every venue's working orders
whatever the desk shows, so a ``kill`` cancel names its ``target_venue`` and is sent there
(``resolve``). Nova's own closes (ADR 048): the day cover and the margin call close a position on
the venue that holds it, so their ``cancel_working`` cancels and their protective ``flatten``
closes name it too. On Live only the day cover may (step 6) -- IBKR liquidates Live itself, so a
margin call never goes there -- and its close only as a market BUY carrying ``intent: "flatten"``,
which the door checks against IBKR's own position (``execution.flatten_intent``), and only while IBKR's
session is the Live Gateway on a live account: the legacy paper Gateway connects too, and its account is not
the one Live's short is in (PR #792 review). Nothing else may name one -- any other place, buy or source is
refused -- and Live only while IBKR, Live's broker, is connected.

Owner: this module (the rules; the lock and the send are ``execution.service``'s).
"""
from __future__ import annotations

from constants_sim import DESK_PRACTICE_VENUES, DESK_VENUE_LIVE, DESK_VENUES
from execution import inflight
from execution.models import ExecutionCommand

TARGET_REFUSED = "TARGET_VENUE_REFUSED"
# ADR 048: the closes Nova makes on a venue whatever the desk shows.
NOVA_CLOSE_ORIGINS = ("day_cover", "margin_call")


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
    kill_cancel = cmd.operation == "cancel" and cmd.source == "kill"
    nova_close = cmd.origin in NOVA_CLOSE_ORIGINS and (
        (cmd.operation == "cancel" and cmd.source == "cancel_working")
        or (cmd.operation == "place" and cmd.source == "flatten" and not cmd.short_entry))
    if not (kill_cancel or nova_close):
        return ("only the kill switch's cancels and Nova's own closes (the day cover, a margin call) may name "
                "a venue other than the desk's -- every other order is sent on the desk's venue")
    if nova_close and target == DESK_VENUE_LIVE and (why := _live_close_refusal(cmd)):
        return why
    if target == DESK_VENUE_LIVE and not ibkr_connected():
        return "Live's orders are IBKR's, and IBKR is not connected -- nothing was sent"
    return None


def live_session_refusal() -> str | None:
    """Why IBKR's session is not Live's -- the Live Gateway on a live account -- or None."""
    from ibkr import client as _client

    mode, kind = _client.account_mode(), _client.broker_account_kind()
    if mode == "live" and kind == "live":
        return None
    return (f"IBKR's session is the {mode} Gateway on a {kind} account, not the Live account -- Live's day cover "
            "goes only to Live; nothing was sent")


def _live_close_refusal(cmd: ExecutionCommand) -> str | None:
    """Why a Nova close may not go to Live, or None: only the day cover, to the Live account, its close a market
    BUY to flat."""
    if cmd.origin != "day_cover":
        return "a margin call never goes to Live -- IBKR liquidates Live itself; nothing was sent"
    if ibkr_connected() and (why := live_session_refusal()):
        return why
    if cmd.operation == "cancel":
        return None
    if (cmd.side or "").upper() != "BUY" or cmd.order_type != "MKT" or getattr(cmd, "intent", None) != "flatten":
        return ("Live's day cover is a market BUY checked against IBKR's own short (intent flatten) -- "
                "nothing was sent")
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

    A short entry -- a place or a bracket -- is held as ``inflight.SHORT`` (ADR 048 gap 5): it
    spends no long, so it never shrinks what a closing SELL may sell, and the next short's borrow
    and margin checks count it. A long bracket holds nothing, as before (its exits close what its
    entry buys).
    """
    if not symbol:
        return
    if getattr(cmd, "short_entry", False) and cmd.operation in ("place", "bracket"):
        qty = cmd.qty if cmd.qty is not None else cmd.shares
        price = cmd.limit_price if cmd.limit_price is not None else cmd.entry_price
        inflight.commit(execution_id, symbol=symbol, side=inflight.SHORT, qty=qty, venue=venue, price=price)
        return
    if cmd.operation != "place":
        return
    inflight.commit(execution_id, symbol=symbol, side=cmd.side, qty=cmd.qty, venue=venue)
