"""Plan flatten / KILL / close tickets so after-hours exits are not RTH MKTs.

Owner: bot.flatten + strategy.executor_flatten + UI closeFullPosition (mirror).
Invalidation: none -- pure clock + quote inputs.
schema_version: n/a.

IBKR ignores outsideRth on MKT (Warning 2109) and holds RTH-only MKTs until
the next regular session (Warning 399 / held_until). Fill now already sweeps
an EH LMT at the opposite quote. Flatten reuses that ticket shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from constants import (
    NOVA_OS_NYSE_HOLIDAYS,
    SESSION_RTH_CLOSE_MIN_ET,
    SESSION_RTH_OPEN_MIN_ET,
)
from market import now_et

FLATTEN_EH_NO_MARK = (
    "After-hours flatten needs a live bid/ask or last -- refusing an RTH-only "
    "MKT that IBKR would hold until the next regular session"
)


@dataclass(frozen=True)
class FlattenExitTicket:
    order_type: str
    outside_rth: bool
    limit_price: float | None
    quote_source: str | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _positive(value: Any) -> float | None:
    try:
        px = float(value)
    except (TypeError, ValueError):
        return None
    if px <= 0:
        return None
    return px


def flatten_needs_extended_hours(now: datetime | None = None) -> bool:
    """True outside weekday RTH (weekend, holiday, premarket, AH, overnight)."""
    when = now or now_et()
    if when.weekday() >= 5:
        return True
    if when.date().isoformat() in NOVA_OS_NYSE_HOLIDAYS:
        return True
    minutes = when.hour * 60 + when.minute
    return not (SESSION_RTH_OPEN_MIN_ET <= minutes < SESSION_RTH_CLOSE_MIN_ET)


# Conftest pins flatten_needs_extended_hours to False so weekend CI does not
# flip existing flatten tests. Tests that need the real clock restore this.
flatten_needs_extended_hours_unpatched = flatten_needs_extended_hours


def flatten_sweep_limit(
    side: str,
    *,
    bid: float | None = None,
    ask: float | None = None,
    last: float | None = None,
) -> tuple[float, str] | None:
    """Aggressive EH limit: hit bid on SELL / ask on BUY, else last."""
    side_u = (side or "").strip().upper()
    opposite = _positive(bid) if side_u == "SELL" else _positive(ask)
    if opposite is not None:
        return opposite, "bid" if side_u == "SELL" else "ask"
    last_px = _positive(last)
    if last_px is not None:
        return last_px, "last"
    return None


def plan_flatten_exit(
    side: str,
    *,
    now: datetime | None = None,
    bid: float | None = None,
    ask: float | None = None,
    last: float | None = None,
    force_extended: bool = False,
) -> FlattenExitTicket:
    """RTH weekday: MKT outside_rth=false. Else EH LMT at bid/ask/last."""
    if force_extended or flatten_needs_extended_hours(now):
        sweep = flatten_sweep_limit(side, bid=bid, ask=ask, last=last)
        if sweep is None:
            return FlattenExitTicket(
                order_type="LMT",
                outside_rth=True,
                limit_price=None,
                quote_source=None,
                error=FLATTEN_EH_NO_MARK,
            )
        px, source = sweep
        return FlattenExitTicket(
            order_type="LMT",
            outside_rth=True,
            limit_price=px,
            quote_source=source,
        )
    return FlattenExitTicket(
        order_type="MKT",
        outside_rth=False,
        limit_price=None,
        quote_source=None,
    )


def resolve_flatten_marks(symbol: str) -> tuple[float | None, float | None, float | None]:
    """Shared-feed bid/ask/last. Never opens reqMktData."""
    from bot.quotes import last_quote, top_of_book
    from ibkr.account_marks import live_l1_last

    bid, ask = top_of_book(symbol)
    last = None
    row = last_quote(symbol) or {}
    last = _positive(row.get("price"))
    if last is None:
        last = live_l1_last(symbol)
    return _positive(bid), _positive(ask), last


def ticket_to_command_fields(ticket: FlattenExitTicket) -> dict[str, Any]:
    return {
        "order_type": ticket.order_type,
        "outside_rth": ticket.outside_rth,
        "limit_price": ticket.limit_price,
    }
