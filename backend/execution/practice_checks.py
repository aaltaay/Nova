"""Practice-venue admission for the execution door (ADR 020; operator decisions, 2026-09-21; ADR 048).

Two checks, both read through the venue's broker so validation and the fill
use one answer. **Admission**: the venue's own market must price the symbol
right now -- the loaded replay at the playhead on Sim, the fresh live last or
recent tape print on Paper; protective sources skip it, because a practice
position can always be closed at the last mark (ADR 018). **No implicit
shorts**: a SELL past the held quantity without ``short_entry`` is refused
``PRACTICE_NO_SHORTS`` on every source, exactly as Invariant #7 keeps it on
Live. A short entry passes here to the short check (``short_sale.door``), which
the door runs under its lock on every venue (ADR 048). The broker repeats both
rules (``practice.order_rules``) for callers that bypass the door.
"""
from __future__ import annotations

from typing import Any

from constants_practice import PRACTICE_NO_SHORTS_CODE, PRACTICE_NO_SHORTS_REASON
from execution.models import ExecutionCommand
from ibkr.safety import PROTECTIVE_SOURCES
from practice import order_rules


def venue_broker(venue: str | None = None) -> Any:
    """The practice venue's broker (Paper or Sim): ``venue``, else the desk's settled one."""
    from practice.broker import for_venue
    from sim.mode import venue as desk_venue

    return for_venue(venue or desk_venue())


def held_qty(broker: Any, symbol: str) -> float:
    """What the practice ledger holds in ``symbol``; a broker without a ledger reads flat (fail closed)."""
    ledger = getattr(broker, "ledger", None)
    if ledger is None:
        return 0.0
    return float(ledger.held_qty(symbol))


def practice_refusal(cmd: ExecutionCommand, venue: str | None = None) -> tuple[str, str] | None:
    """``(detail, reason_code)`` when a practice venue refuses ``cmd``; ``None`` to admit it."""
    if cmd.operation not in ("place", "bracket"):
        return None
    broker = venue_broker(venue)
    symbol = cmd.normalized_symbol() or ""
    if cmd.source not in PROTECTIVE_SOURCES:
        ok, reason, code = broker.reference.admission(symbol)
        if not ok:
            return reason, code
    if getattr(cmd, "intent", None) == "flatten":
        # The ticket's Flatten is answered in the account stage, under the
        # execution lock (execution.flatten_intent): FLATTEN_NOT_A_CLOSE says why
        # a close was refused. "No short entries" misnamed a Flatten pressed on
        # a flat position (2026-09-23 test run). The practice broker still
        # cancels, at the fill, any SELL past what is held.
        return None
    if getattr(cmd, "short_entry", False):
        return None  # the short check judges it, under the lock (short_sale.door)
    side = cmd.side or ""
    qty = float(cmd.qty or cmd.shares or 0)
    if cmd.operation == "place" and order_rules.opening_short(held_qty(broker, symbol), side, qty):
        return PRACTICE_NO_SHORTS_REASON, PRACTICE_NO_SHORTS_CODE
    return None
