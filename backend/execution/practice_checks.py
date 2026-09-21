"""Practice-venue admission for the execution door (ADR 020; operator decisions, 2026-09-21).

Two checks, both read through the venue's broker so validation and the fill
use one answer. **Admission**: the venue's own market must price the symbol
right now -- the loaded replay at the playhead on Sim, the fresh live last or
recent tape print on Paper; protective sources skip it, because a practice
position can always be closed at the last mark (ADR 018). **No shorts**: a
SELL is only ever risk-reducing -- an opening short (a SELL beyond the held
quantity, or ``short_entry``) is refused ``PRACTICE_NO_SHORTS`` on every
source, exactly as Invariant #7 keeps SELL risk-reducing on Live. The broker
repeats the same check (``practice.order_rules``) for callers that bypass the
door.
"""
from __future__ import annotations

from typing import Any

from constants_practice import PRACTICE_NO_SHORTS_CODE, PRACTICE_NO_SHORTS_REASON
from execution.models import ExecutionCommand
from ibkr.safety import PROTECTIVE_SOURCES
from practice import order_rules


def venue_broker() -> Any:
    """The settled practice venue's broker (Paper or Sim)."""
    from practice.broker import for_venue
    from sim.mode import venue

    return for_venue(venue())


def held_qty(broker: Any, symbol: str) -> float:
    """What the practice ledger holds in ``symbol``; a broker without a ledger reads flat (fail closed)."""
    ledger = getattr(broker, "ledger", None)
    if ledger is None:
        return 0.0
    return float(ledger.held_qty(symbol))


def practice_refusal(cmd: ExecutionCommand) -> tuple[str, str] | None:
    """``(detail, reason_code)`` when a practice venue refuses ``cmd``; ``None`` to admit it."""
    if cmd.operation not in ("place", "bracket"):
        return None
    broker = venue_broker()
    symbol = cmd.normalized_symbol() or ""
    if cmd.source not in PROTECTIVE_SOURCES:
        ok, reason, code = broker.reference.admission(symbol)
        if not ok:
            return reason, code
    short = bool(getattr(cmd, "short_entry", False))
    side = "SELL" if (cmd.operation == "bracket" and short) else (cmd.side or "")
    qty = float(cmd.qty or cmd.shares or 0)
    if order_rules.opening_short(held_qty(broker, symbol), side, qty, short):
        return PRACTICE_NO_SHORTS_REASON, PRACTICE_NO_SHORTS_CODE
    return None
