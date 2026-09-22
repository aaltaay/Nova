"""Per-order rules the practice venues enforce (operator decisions, 2026-09-21).

**Time-in-force.** ``ExecutionCommand.tif`` (#91) reaches the practice broker
unchanged. A ``DAY`` order carries ``expires_ts`` -- the close of the session
it was placed in, as the venue's reference names it (``session_close_ts``: the
session clock's window end on Sim, the next ``PRACTICE_SESSION_CLOSE_HOUR_ET``
America/New_York on Paper) -- and a print after that second never fills it.
``expire_due`` turns every due order into an ``expired`` ledger event (row
status ``Expired``, ``PRACTICE_TIF_EXPIRED``) stamped at the close itself, so
Sim time travel back before the close restores the order like any other
event, and a Paper pass after a restart records the truth: it expired at the
close. ``GTC`` carries no expiry and persists across days and restarts.

**No shorts.** A SELL is only ever risk-reducing, exactly as Invariant #7
keeps it on Live: a SELL for more than the held quantity, or any order
carrying ``short_entry``, is an opening short and is refused
``PRACTICE_NO_SHORTS``. The execution door checks it at admission
(``execution.practice_checks``) and the broker checks it again. Nothing is
inferred from side plus a flat position beyond that arithmetic.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from constants_practice import (
    PRACTICE_SESSION_CLOSE_HOUR_ET,
    PRACTICE_TIF_DAY,
    PRACTICE_TIF_EXPIRED_CODE,
    PRACTICE_TIF_EXPIRED_REASON,
    PRACTICE_TIF_GTC,
    PRACTICE_TIFS,
)
from market import regular_hours_at
from practice.clock import at

_EPS = 1e-9

TIF_REASON = f"tif must be one of {', '.join(PRACTICE_TIFS)}"
# The ADR 007 source stamped on an expiry: the venue itself, never a caller.
EXPIRY_SOURCE = "venue"


def normalize_tif(raw: str | None) -> str | None:
    """``DAY`` / ``GTC`` for a value Nova places (blank means DAY); ``None`` otherwise."""
    text = (raw or "").strip().upper() or PRACTICE_TIF_DAY
    return text if text in PRACTICE_TIFS else None


def next_close_after(ts: float) -> float:
    """The first ``PRACTICE_SESSION_CLOSE_HOUR_ET`` America/New_York strictly after ``ts``.

    An order placed at or after the close belongs to the next session, which
    is IBKR's rule for a DAY order placed after hours.
    """
    now = at(ts)
    close = now.replace(hour=PRACTICE_SESSION_CLOSE_HOUR_ET, minute=0, second=0, microsecond=0)
    if now >= close:
        close += timedelta(days=1)
    return close.timestamp()


def session_close_ts(reference: Any, ts: float) -> float:
    """When the session ``ts`` belongs to closes, as the venue's reference names it.

    ``ReplayReference`` answers with the session clock's window end (the
    replayed session's close), ``LiveReference`` with ``next_close_after``; a
    reference without the method (a test double) gets the Paper rule.
    """
    fn = getattr(reference, "session_close_ts", None)
    if callable(fn):
        return float(fn(ts))
    return next_close_after(ts)


def expiry_ts(tif: str, reference: Any, placed_ts: float) -> float | None:
    """``None`` for GTC; for DAY, the close of the session the order was placed in."""
    if tif == PRACTICE_TIF_GTC:
        return None
    return session_close_ts(reference, placed_ts)


def opening_short(held_qty: float, side: str, qty: float, short_entry: bool = False) -> bool:
    """True when the order would open or add to a short.

    An explicit ``short_entry`` is an opening short whatever the side; a SELL
    is one when it sells more than the account holds.
    """
    if short_entry:
        return True
    if (side or "").strip().upper() != "SELL":
        return False
    return float(qty) > float(held_qty) + _EPS


def mkt_outside_rth(order_type: str | None, now_ts: float, protective: bool = False) -> bool:
    """A non-protective MKT at a moment outside regular hours -- refused ``MKT_OUTSIDE_RTH``.

    ``now_ts`` is the venue's clock (the replay playhead on Sim), so a replayed
    10:00 is regular hours whatever the wall clock says. Protective closes are
    exempt: a practice position can always get flat (ADR 018).
    """
    if protective or (order_type or "").strip().upper() != "MKT":
        return False
    return not regular_hours_at(at(now_ts))


# The conftest pins mkt_outside_rth to False so after-hours and weekend CI
# does not flip every MKT test; tests about the gate restore this.
mkt_outside_rth_unpatched = mkt_outside_rth


def due(row: dict[str, Any], now_ts: float) -> bool:
    """The working ``row`` has reached its session close at ``now_ts``."""
    expires = row.get("expires_ts")
    return expires is not None and float(now_ts) >= float(expires) - _EPS


def print_after_expiry(row: dict[str, Any], print_ts: float) -> bool:
    """A DAY order never fills on a print after its session closed."""
    expires = row.get("expires_ts")
    return expires is not None and float(print_ts) > float(expires) + _EPS


def expire_due(ledger: Any, now_ts: float) -> list[dict[str, Any]]:
    """Expire every working order that is due at ``now_ts``; returns the closed rows.

    The event is stamped at the order's own close, not at ``now_ts``: on Paper
    a pass after a restart records when it really expired, on Sim a scrub back
    before the close drops the event and the order rests again.
    """
    from practice.ledger import EVENT_EXPIRED

    expired: list[dict[str, Any]] = []
    for row in ledger.working_orders():
        if not due(row, now_ts):
            continue
        closed = ledger.cancel(
            int(row["order_id"]), ts=float(row["expires_ts"]), reason=PRACTICE_TIF_EXPIRED_REASON,
            code=PRACTICE_TIF_EXPIRED_CODE, source=EXPIRY_SOURCE, kind=EVENT_EXPIRED,
        )
        if closed is not None:
            expired.append(closed)
    return expired


def admission_price(
    typ: str, side: str, limit_price: float | None, stop_price: float | None, ref: Any,
) -> float | None:
    """What an opening order is charged against buying power at admission.

    ``ref`` is the venue's ``fill_model.Reference`` (or None when it has none).
    """
    if typ == "LMT" and limit_price is not None:
        return float(limit_price)
    if typ == "STP" and stop_price is not None:
        return float(stop_price)
    if ref is None:
        return None
    quoted = ref.ask if side == "BUY" else ref.bid
    touch = quoted if quoted is not None else ref.last
    return float(touch) if touch is not None else None
