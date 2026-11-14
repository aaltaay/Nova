"""Paper's round trips in the trade journal (ADR 069 decision 6, ``architecture/schema/journal.md``).

Built from the practice ledger, never inside a fill: ``practice.history.ledger_fills`` gives each Paper fill's
``parts`` -- how it split across the stock's holders, each at its holder's own cost -- and each holder's shares
in a stock make one round trip, from leaving zero to returning to it. So you and the Live Trader trading SOFI at
once are two trades, and Nova's own closes (KILL, the day cover) close each holder's own. A round trip's P&L is
the sum of its parts' realized, net of commission and fees, so the trades add up to the books' realized. Its
stop is the stop leg sent with the entry, when it sits on the losing side; R-multiples skip a trade without one.

``sync`` brings the journal up to the Paper ledger and its archives when a Reports read asks for Paper: a new
round trip is added and a stored one whose figures changed is rewritten by ``close_key``
(``journal.store.upsert_round_trips``); nothing is deleted. It does that work once per ledger change, so the
first open fills in every past Paper day and a poll with nothing new writes nothing.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any

from constants_owners import JOURNAL_VENUE_PAPER, OWNER_YOU
from owners.whose import book_of, bot_of
from practice.ledger import EVENT_PLACED, Ledger

logger = logging.getLogger(__name__)

_EPS = 1e-6
_PRICE_PLACES = 6
_MONEY_PLACES = 2    # to the cent, so the calendar's sums and the drawdown's agree to the cent

_lock = threading.Lock()
_synced: tuple | None = None   # what the last sync read: the journal file and every ledger's stamp


@dataclass
class _Trip:
    symbol: str
    holder: str
    long: bool
    opened_ts: float
    open_order_id: int
    net: float = 0.0
    in_qty: float = 0.0
    in_notional: float = 0.0
    out_qty: float = 0.0
    out_notional: float = 0.0
    pnl: float = 0.0
    costs: float = 0.0
    orders: list[int] = field(default_factory=list)
    closed_by: str | None = None      # ``you``: you closed it after its trader handed it to you (ADR 072)


def _entry_stops(ledger: Ledger) -> dict[int, float]:
    """Each entry's stop leg as it was first sent: the opening order's id -> its stop price."""
    stops: dict[int, float] = {}
    for event in ledger.events:
        row = event.get("row") if event.get("type") == EVENT_PLACED else None
        if not isinstance(row, dict) or row.get("order_type") not in ("STP", "STP LMT"):
            continue
        parent, stop = row.get("parent_id"), row.get("stop_price")
        if parent and stop:
            stops.setdefault(int(parent), float(stop))
    return stops


def _row(ledger: Ledger, trip: _Trip, closed_ts: float, stops: dict[int, float]) -> dict[str, Any]:
    entry = trip.in_notional / trip.in_qty
    stop = stops.get(trip.open_order_id)
    if stop is not None and not (stop < entry if trip.long else stop > entry):
        stop = None    # a stop on the winning side plans no risk
    return {
        "symbol": trip.symbol,
        "setup": None,
        "side": "long" if trip.long else "short",
        "qty": int(round(trip.out_qty)),
        "entry_price": round(entry, _PRICE_PLACES),
        "exit_price": round(trip.out_notional / trip.out_qty, _PRICE_PLACES),
        "stop_price": stop,
        "pnl": round(trip.pnl, _MONEY_PLACES),
        "commission": round(trip.costs, _MONEY_PLACES),
        "opened_ts": trip.opened_ts,
        "closed_ts": closed_ts,
        "fill_ids": ",".join(str(order_id) for order_id in trip.orders),
        "close_key": (f"{JOURNAL_VENUE_PAPER}:{ledger.created_ts:.0f}:{trip.holder}:{trip.symbol}:"
                      f"{trip.open_order_id}:{trip.opened_ts:.3f}"),
        "owner": book_of(trip.holder),
        "bot": bot_of(trip.holder),
        "closed_by": trip.closed_by,
    }


def round_trips(ledger: Ledger) -> list[dict[str, Any]]:
    """``ledger``'s closed round trips, one per holder, oldest close first, as journal rows. A ledger that keeps
    no books (Sim) has none; a holder's position still open is not one yet."""
    from practice.history import ledger_fills

    stops = _entry_stops(ledger)
    open_trips: dict[tuple[str, str], _Trip] = {}
    out: list[dict[str, Any]] = []
    for fill in ledger_fills(ledger):
        buy = fill["side"] == "BUY"
        for part in fill.get("parts") or ():
            holder = part["bot"] or part["owner"]   # a retired bot by its origin; you, Claude, the brain
            key = (fill["symbol"], holder)
            trip = open_trips.get(key)
            if trip is None:
                if part["closes"]:   # shares this ledger never saw open: no round trip of its own
                    continue
                trip = open_trips[key] = _Trip(fill["symbol"], holder, buy, float(fill["ts"]), int(fill["order_id"]))
            qty, price = float(part["qty"]), float(fill["price"])
            if part["closes"]:
                trip.out_qty += qty
                trip.out_notional += qty * price
                if part.get("closed_by") == OWNER_YOU:
                    trip.closed_by = OWNER_YOU
            else:
                trip.in_qty += qty
                trip.in_notional += qty * price
            trip.net += qty if buy else -qty
            trip.pnl += float(part["realized"])
            trip.costs += float(part["commission"]) + float(part["fees"])
            if int(fill["order_id"]) not in trip.orders:
                trip.orders.append(int(fill["order_id"]))
            if part["closes"] and abs(trip.net) < _EPS:
                out.append(_row(ledger, open_trips.pop(key), float(fill["ts"]), stops))
    return out


def _archive_stamp(persist_path: str | None) -> tuple:
    """The archives beside the Paper ledger, as names, sizes and times -- read without parsing them."""
    if not persist_path:
        return ()
    from practice import persist

    try:
        paths = persist.list_archives(persist_path)
        return tuple((p, os.path.getsize(p), os.path.getmtime(p)) for p in paths)
    except OSError as exc:
        logger.warning("JOURNAL paper trips: cannot read the archives beside %s: %s", persist_path, exc)
        return ()


def sync_ledgers(ledgers: list[Ledger]) -> int:
    """Write ``ledgers``' round trips into the journal; returns how many rows were added or rewritten."""
    from journal.store import upsert_round_trips

    rows = [row for ledger in ledgers for row in round_trips(ledger)]
    return upsert_round_trips(rows, venue=JOURNAL_VENUE_PAPER)


def sync() -> int:
    """Bring the journal's Paper round trips up to the Paper ledger and its archives, once per change."""
    global _synced
    from journal.db import db_path
    from practice import history
    from practice.broker import for_venue

    broker = for_venue(JOURNAL_VENUE_PAPER)
    ledger = broker.ledger
    stamp = (str(db_path()), _archive_stamp(broker.persist_path), ledger.created_ts, len(ledger.events))
    with _lock:
        if stamp == _synced:
            return 0
        archives, warnings = history.load_archives(broker.persist_path)
        for warning in warnings:
            logger.warning("JOURNAL paper trips: %s", warning)
        written = sync_ledgers([*(old for _, old in archives), ledger])
        _synced = stamp
    if written:
        logger.info("JOURNAL paper trips: %d round trip(s) written from the Paper ledger", written)
    return written


def reset_for_tests() -> None:
    global _synced
    with _lock:
        _synced = None
