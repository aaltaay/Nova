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

**No implicit shorts, and no flips** (ADR 048). A short is never inferred: a
SELL for more than the held quantity without ``short_entry`` is refused
``PRACTICE_NO_SHORTS``, exactly as Invariant #7 keeps it on Live. A short entry
is a SELL that opens from flat or adds to a short; while the account holds the
stock long it is refused ``PRACTICE_SHORT_WHILE_LONG``, at placement and at the
fill, and one whose fill would come outside the short hours (09:35 to 15:50 ET by
the venue's clock) is cancelled ``SHORT_HOURS`` at the fill. The execution door's
short check judges everything else (``short_sale``), and the broker repeats these
rules for callers that bypass the door.

**Never past flat at the fill** (ADR 048 gap 8). A row records what it does to the position when
it is placed (``side_fields``: ``short_entry``, ``position_side``, ``effect``). A cover -- a BUY
placed against a short -- that would buy past flat when its print arrives, because another cover
filled first, is cancelled ``PRACTICE_OVERCOVER``, as a SELL past the long is (QA R42).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from constants_practice import (
    PRACTICE_BUYING_POWER_CODE,
    PRACTICE_BUYING_POWER_REASON,
    PRACTICE_NO_SHORTS_CODE,
    PRACTICE_NO_SHORTS_REASON,
    PRACTICE_OVERCOVER_CODE,
    PRACTICE_OVERCOVER_REASON,
    PRACTICE_SHORT_WHILE_LONG_CODE,
    PRACTICE_SHORT_WHILE_LONG_REASON,
    PRACTICE_SESSION_CLOSE_HOUR_ET,
    PRACTICE_TIF_DAY,
    PRACTICE_TIF_EXPIRED_CODE,
    PRACTICE_TIF_EXPIRED_REASON,
    PRACTICE_TIF_GTC,
    PRACTICE_TIFS,
)
from constants_shorts import SHORT_HOURS
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


def short_entry_refusal(held_qty: float, side: str) -> tuple[str, str] | None:
    """``(reason, code)`` when a short entry may not open: it is a SELL, from flat or adding to a short."""
    if (side or "").strip().upper() != "SELL":
        return "short_entry requires side=SELL", "SIDE_INVALID"
    if float(held_qty) > _EPS:
        return f"{PRACTICE_SHORT_WHILE_LONG_REASON} -- {float(held_qty):g} held", PRACTICE_SHORT_WHILE_LONG_CODE
    return None


def side_fields(side: str, held: float, short_entry: bool = False) -> dict[str, Any]:
    """What an order does to the position it trades, as Nova knew it when the order was placed.

    ``{short_entry, position_side: "long" | "short", effect: "opens" | "closes"}``: a short entry
    opens a short; a BUY against a short covers it; any other BUY opens or adds to a long; a SELL
    against a long closes it (ADR 048: the Orders table's Side column reads these).
    """
    if short_entry:
        return {"short_entry": True, "position_side": "short", "effect": "opens"}
    if (side or "").strip().upper() == "BUY":
        covering = float(held) < -_EPS
        return {"short_entry": False, "position_side": "short" if covering else "long",
                "effect": "closes" if covering else "opens"}
    return {"short_entry": False, "position_side": "long", "effect": "closes"}


def exit_side_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """A bracket exit closes the position its entry opens: the entry's side, ``closes``."""
    return {"short_entry": False, "position_side": entry.get("position_side") or "long", "effect": "closes"}


def entered_ts(row: dict[str, Any]) -> float:
    """When ``row`` was first placed, by the venue's clock: a replace re-dates ``placed_ts``, never this.

    A row without the ledger's ``entered_ts`` (a test double) reads its ``placed_ts``; neither reads 0,
    which no short session holds, so such a short entry lapses rather than rests.
    """
    for key in ("entered_ts", "placed_ts"):
        value = row.get(key)
        if value is not None:
            return float(value)
    return 0.0


def fill_refusal(ledger: Any, row: dict[str, Any], price: float,
                 fill_ts: float | None = None) -> tuple[str, str] | None:
    """``(reason, code)`` when a working order may not fill at ``price`` now; ``None`` to fill it.

    A SELL past the held quantity would open a short nobody asked for -- another
    close filled first (QA R42: two flattens both rested and both filled, leaving
    the Sim account short) -- and a short entry never fills against a long, nor at
    ``fill_ts`` (the fill's time) outside the short hours of the day it was placed: a Sim jump
    past 15:50 fills on the prints it crossed before the runner's cutoff pass (ADR 048 1.9), and
    a GTC entry Nova was closed over meets the next day's prints first. A cover past flat
    would turn the short into a long (ADR 048 gap 8). A BUY the account can no
    longer afford is refused as at admission. Either way the order is cancelled
    at the fill, never filled.
    """
    symbol, side, qty = str(row["symbol"]), str(row["side"]), float(row["qty"])
    held = float(ledger.held_qty(symbol))
    if row.get("short_entry"):
        refused = short_entry_refusal(held, side)  # a long opened since it was placed: never flip
        if refused is not None:
            return refused[0] + " when this short would fill", refused[1]
        if fill_ts is not None:
            from short_sale import hours as short_hours

            closed = short_hours.entry_lapsed(entered_ts(row), float(fill_ts))
            if closed is not None:
                return f"{closed} This short entry was cancelled at its fill.", SHORT_HOURS
    elif opening_short(held, side, qty):
        return (
            f"{PRACTICE_NO_SHORTS_REASON} -- {held:g} held when this SELL {qty:g} would fill",
            PRACTICE_NO_SHORTS_CODE,
        )
    if side.strip().upper() == "BUY" and (row.get("effect") == "closes" or held < -_EPS):
        short = max(0.0, -held)
        if qty > short + _EPS:
            return (
                f"{PRACTICE_OVERCOVER_REASON} -- {short:g} short when this BUY {qty:g} would fill",
                PRACTICE_OVERCOVER_CODE,
            )
    ok, needed, available = ledger.can_afford(symbol, side, qty, price)
    if not ok:
        return (
            f"{PRACTICE_BUYING_POWER_REASON} at the fill (needs {needed:,.2f}, has {available:,.2f})",
            PRACTICE_BUYING_POWER_CODE,
        )
    return None


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
