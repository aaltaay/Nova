"""Kill-switch cancel sweep -- every venue's working orders, every cancel through the door (ADR 007).

Spec D (2026-09-30), #656: the sweep used to stop at "is IBKR connected?" and read only the desk's
venue, so on Paper with the Gateway down, or on a Sim replay, it reported nothing cancelled while
practice orders kept resting and filling. Now it reads and cancels each venue that can hold a
working order, whatever the desk shows:

- **Live** while IBKR is connected (its own open trades, never the practice ledger); otherwise it
  says so: ``"Gateway disconnected: Live orders were not swept"``.
- **Paper** always -- its ledger is local and persistent, readable with the Gateway dark.
- **Sim** when this process has a Sim scratch ledger loaded (nothing loaded holds no order).

Each cancel is a ``kill`` cancel with an explicit ``target_venue`` (``execution.venue_door``). A
read that fails is that venue's ``error`` -- never "nothing to cancel" -- and a refused cancel is
listed in ``failed`` with its reason. The sweep runs on the caller's loop (the async route), the
loop every other order runs on: it used to run ``execute`` under ``asyncio.run`` from a sync route,
a second event loop that raised "bound to a different event loop" on the door's lock whenever an
order held it (#656).

**Protective stops stay resting** (ADR 048 gap 6, the operator's decision): working stops (STP,
STP LMT, TRAIL) on the side that closes a position the venue holds -- SELL stops under a long, BUY
stops over a short -- are kept, together no larger than the position, and listed in ``kept`` with
why; entries and targets are still cancelled. Two stops that each cover the whole position would
both fill and flip it, so the stops are kept in turn until the next would pass the position. An
order Nova cannot cancel rests whatever the sweep does, so a closing one takes its room first; then
Nova's stops, the nearest the market first (it limits the loss most), then the oldest. The rest are
cancelled, and the venue's ``note`` names them. A bracket's stop whose entry is still working with
nothing filled protects nothing yet and is cancelled with it (its ``parent_id`` names that entry:
Live rows carry IBKR's ``parentId``). When the venue's positions cannot be read no stop can be told
protective: every order is cancelled, as before, and the venue's ``note`` says so.

Owns no state.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from constants_sim import DESK_VENUE_LIVE, DESK_VENUE_PAPER, DESK_VENUE_SIM

logger = logging.getLogger(__name__)

LIVE_DISCONNECTED = "Gateway disconnected: Live orders were not swept"
LIVE_NOT_READY = "IBKR is still connecting (session not ready): Live orders were not swept"
SIM_NOT_LOADED = "Sim's scratch account is not open in this process, so it holds no working order."
VENUES = (DESK_VENUE_LIVE, DESK_VENUE_PAPER, DESK_VENUE_SIM)   # real money first

Rows = list[dict[str, Any]]


def _live_rows() -> tuple[Rows | None, str | None, str | None]:
    """IBKR's own working orders -- never the desk's practice ledger (``ibkr.live_book``)."""
    from ibkr import client as _client
    from ibkr import live_book

    if not _client.is_connected():
        return None, LIVE_DISCONNECTED, None
    if _client.get_ib() is None:
        return None, LIVE_NOT_READY, None
    return live_book.open_rows(), None, None


def _paper_rows() -> tuple[Rows | None, str | None, str | None]:
    from practice.broker import for_venue

    return for_venue(DESK_VENUE_PAPER).working_orders(), None, None


def _sim_rows() -> tuple[Rows | None, str | None, str | None]:
    from practice.broker import loaded

    broker = loaded(DESK_VENUE_SIM)
    if broker is None:
        return [], None, SIM_NOT_LOADED
    return broker.working_orders(), None, None


_STOP_TYPES = frozenset({"STP", "STP LMT", "TRAIL", "TRAIL LIMIT"})
_TRAIL_TYPES = frozenset({"TRAIL", "TRAIL LIMIT"})   # their stop_price is the trail amount, not a trigger
_WAITING = frozenset({"PreSubmitted", "PendingSubmit"})
_EPS = 1e-9
POSITIONS_UNREAD = "its positions could not be read, so no stop could be told protective: every order was cancelled"


def _live_held() -> dict[str, float]:
    """IBKR's own positions, signed (never the desk's practice ledger; ``ibkr.live_book``)."""
    from ibkr import live_book

    return live_book.positions()


def _practice_held(venue: str) -> dict[str, float]:
    from practice.broker import for_venue, loaded

    broker = for_venue(venue) if venue == DESK_VENUE_PAPER else loaded(venue)
    if broker is None:
        return {}
    ledger = broker.ledger
    return {sym: float(ledger.held_qty(sym)) for sym in ledger.held_symbols()}


def held_positions(venue: str) -> dict[str, float] | None:
    """``{SYMBOL: signed qty}`` the venue holds; None when they cannot be read (logged)."""
    try:
        return _live_held() if venue == DESK_VENUE_LIVE else _practice_held(venue)
    except Exception:
        logger.exception("kill: %s's positions could not be read -- no stop is kept", venue)
        return None


def _filled(row: dict[str, Any]) -> float:
    try:
        return float(row.get("filled_qty") or 0)
    except (TypeError, ValueError):
        return 0.0


def unfilled_entries(rows: Rows) -> set[int]:
    """Order ids of the venue's working orders that have filled nothing: entries a bracket exit may wait on."""
    return {oid for row in rows if (oid := _order_id(row)) is not None and oid > 0 and _filled(row) <= _EPS}


def _waits_on_entry(row: dict[str, Any], unfilled: set[int] | None) -> bool:
    """A bracket exit whose entry is still working and has bought nothing: it closes nothing held yet.

    With the venue's working orders (``unfilled_entries``), the entry's own row decides: on Live a
    stop IBKR holds PreSubmitted after its entry filled still protects, and once an entry has filled
    some IBKR may already work its exits. Without them, the row's status does.
    """
    parent = row.get("parent_id")
    if parent is None:
        return False
    if unfilled is not None:
        try:
            return int(parent) in unfilled
        except (TypeError, ValueError):
            return True   # a parent Nova cannot read: never kept as protective
    return str(row.get("status") or "") in _WAITING


def _closing_qty(row: dict[str, Any], held: dict[str, float],
                 unfilled: set[int] | None) -> tuple[str, float, float] | None:
    """``(symbol, open qty, signed position)`` when ``row`` would close a held position if it filled.

    None for an order on the opening side, one with nothing open, or a bracket exit waiting on its entry.
    """
    if _waits_on_entry(row, unfilled):
        return None   # a bracket exit waiting on its entry closes nothing held yet
    symbol = str(row.get("symbol") or "").strip().upper()
    side = str(row.get("side") or "").strip().upper()
    position = float(held.get(symbol, 0.0))
    try:
        remaining = row.get("remaining_qty")
        open_qty = float(remaining if remaining is not None else row.get("qty") or 0)
    except (TypeError, ValueError):
        return None
    closes = (side == "SELL" and position > _EPS) or (side == "BUY" and position < -_EPS)
    if not closes or open_qty <= _EPS:
        return None
    return symbol, open_qty, position


def _is_stop(row: dict[str, Any]) -> bool:
    return str(row.get("order_type") or "").strip().upper() in _STOP_TYPES


def _closing_stop(row: dict[str, Any], held: dict[str, float],
                  unfilled: set[int] | None) -> tuple[str, float, float] | None:
    """``(symbol, open qty, signed position)`` when ``row`` is a stop that closes a held position by
    itself (no larger than it); None when it is anything else."""
    if not _is_stop(row):
        return None
    judged = _closing_qty(row, held, unfilled)
    if judged is None or judged[1] > abs(judged[2]) + _EPS:
        return None
    return judged


def _why(symbol: str, qty: float, position: float) -> str:
    kind = "long" if position > 0 else "short"
    if qty >= abs(position) - _EPS:
        return f"protects the {abs(position):g} {symbol} {kind}"
    return f"protects {qty:g} of the {abs(position):g} {symbol} {kind}"


def protective_stop(row: dict[str, Any], held: dict[str, float], unfilled: set[int] | None = None) -> str | None:
    """Why ``row`` alone would be a stop protecting a held position, or None to cancel it.

    One row at a time; the sweep also caps the stops it keeps at the position (``kept_stops``).
    """
    judged = _closing_stop(row, held, unfilled)
    return None if judged is None else _why(*judged)


def _trigger(row: dict[str, Any]) -> float | None:
    """The price a stop fires at, when its row says (a trailing stop's ``stop_price`` is its trail)."""
    if str(row.get("order_type") or "").strip().upper() in _TRAIL_TYPES:
        return None
    try:
        price = float(row.get("stop_price"))
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _keep_order(row: dict[str, Any], position: float) -> tuple[int, float, int]:
    """Which of Nova's stops is kept first: the nearest the market (it limits the loss most), then the oldest."""
    trigger = _trigger(row)
    if trigger is None:
        nearest = (1, 0.0)
    else:   # a long's SELL stop nearer the market is higher; a short's BUY stop is lower
        nearest = (0, -trigger if position > 0 else trigger)
    return nearest[0], nearest[1], _order_id(row) or 0


def kept_stops(rows: Rows, held: dict[str, float]) -> tuple[dict[int, str], list[str]]:
    """``({row index: why}, [what was not kept and why])`` for one venue's working orders.

    The stops kept on a position, with the closing orders Nova cannot cancel, never pass it: two
    stops that each cover it would both fill and flip it. An order Nova cannot cancel (no API order
    id) rests whatever the sweep does, so it takes its room first -- a stop among them is listed as
    kept when it fits, and any other is named as a problem by the sweep.
    """
    unfilled = unfilled_entries(rows)
    taken: dict[str, float] = {}
    kept: dict[int, str] = {}
    candidates: dict[str, list[tuple[tuple[int, float, int], int, float]]] = {}
    for index, row in enumerate(rows):
        order_id = _order_id(row)
        if order_id is None or order_id <= 0:
            judged = _closing_qty(row, held, unfilled)
            if judged is not None:
                symbol, open_qty, position = judged
                fits = _is_stop(row) and taken.get(symbol, 0.0) + open_qty <= abs(position) + _EPS
                taken[symbol] = taken.get(symbol, 0.0) + open_qty
                if fits:
                    kept[index] = _why(symbol, open_qty, position)
            continue
        judged = _closing_stop(row, held, unfilled)
        if judged is not None:
            symbol, open_qty, position = judged
            candidates.setdefault(symbol, []).append((_keep_order(row, position), index, open_qty))
    dropped: list[str] = []
    for symbol, stops in candidates.items():
        position = held[symbol]
        room = abs(position) - taken.get(symbol, 0.0)
        kind = "long" if position > 0 else "short"
        for _, index, open_qty in sorted(stops):
            if open_qty > room + _EPS:
                dropped.append(f"order {_order_id(rows[index])} ({symbol} stop, {open_qty:g}): keeping it too would "
                               f"take the closing orders past the {abs(position):g} {symbol} {kind}")
                continue
            room -= open_qty
            kept[index] = _why(symbol, open_qty, position)
    return kept, dropped


def read_working(venue: str) -> tuple[Rows | None, str | None, str | None]:
    """``(rows, error, note)``: ``venue``'s working orders, or None with why they could not be read."""
    readers: dict[str, Callable[[], tuple[Rows | None, str | None, str | None]]] = {
        DESK_VENUE_LIVE: _live_rows, DESK_VENUE_PAPER: _paper_rows, DESK_VENUE_SIM: _sim_rows,
    }
    try:
        return readers[venue]()
    except Exception as exc:
        logger.exception("kill: %s's working orders could not be read -- that venue was not swept", venue)
        return None, f"{venue.capitalize()}'s working orders could not be read ({exc}): not swept", None


async def cancel_via_door(venue: str, order_id: int, symbol: str | None) -> tuple[bool, str | None]:
    """One ``kill`` cancel aimed at ``venue`` through ``execution.service.execute``; ``(ok, error)``."""
    from execution.models import ExecutionCommand
    from execution.service import execute

    receipt = await execute(
        ExecutionCommand(
            operation="cancel",
            idempotency_key=f"kill:cancel:{venue}:{order_id}:{uuid.uuid4()}",
            source="kill",
            order_id=order_id,
            symbol=symbol,
            skip_risk=True,
            target_venue=venue,
        ),
        wait_ack=False,
    )
    return bool(receipt.ok), receipt.error


def _order_id(row: dict[str, Any]) -> int | None:
    try:
        return int(row.get("order_id"))
    except (TypeError, ValueError):
        return None


async def sweep_venue(venue: str) -> dict[str, Any]:
    """``{venue, cancelled, failed, kept, error, note}`` for one venue's working orders."""
    rows, error, note = read_working(venue)
    out: dict[str, Any] = {"venue": venue, "cancelled": [], "failed": [], "kept": [], "error": error, "note": note}
    if rows is None:
        return out
    held = held_positions(venue) if rows else {}
    kept: dict[int, str] = {}
    if held is None:
        out["note"] = "; ".join(part for part in (note, POSITIONS_UNREAD) if part)
    else:
        kept, dropped = kept_stops(rows, held)
        if dropped:
            out["note"] = "; ".join(part for part in (note, "stops beyond the position were cancelled: "
                                                      + "; ".join(dropped)) if part)
    problems: list[str] = []
    for index, row in enumerate(rows):
        order_id = _order_id(row)
        why_kept = kept.get(index)
        if why_kept is not None:
            out["kept"].append({
                "order_id": order_id, "symbol": row.get("symbol"), "side": row.get("side"),
                "qty": row.get("remaining_qty") if row.get("remaining_qty") is not None else row.get("qty"),
                "order_type": row.get("order_type"), "stop_price": row.get("stop_price"), "why": why_kept,
            })
            continue
        if order_id is None or order_id <= 0:
            # An order Nova's API session did not place (TWS shows it with id 0): Nova cannot cancel it.
            problems.append(f"an order ({row.get('symbol') or '?'}, perm id {row.get('perm_id') or '?'}) "
                            "has no API order id -- cancel it in TWS")
            continue
        try:
            ok, why = await cancel_via_door(venue, order_id, str(row.get("symbol") or "") or None)
        except Exception as exc:
            logger.exception("kill: the %s cancel of order %s raised", venue, order_id)
            ok, why = False, f"{type(exc).__name__}: {exc}"
        if ok:
            out["cancelled"].append(order_id)
        else:
            out["failed"].append(order_id)
            problems.append(f"order {order_id}: {why or 'refused'}")
    if problems:
        out["error"] = "; ".join(problems)
    return out


async def sweep_every_venue() -> list[dict[str, Any]]:
    """Every venue's sweep, Live first: ``[{venue, cancelled, failed, kept, error, note}]``."""
    return [await sweep_venue(venue) for venue in VENUES]
