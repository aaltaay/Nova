"""AllLast + depth feeder; all disk writes run on the existing fenced capture worker."""

import logging
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from capture import worker
from capture.constants_capture import (
    CAPTURE_BOOK_BATCH_MAX,
    CAPTURE_BOOK_BATCH_SEC,
    CAPTURE_L2_MAX_HZ,
    CAPTURE_PRINT_BATCH_MAX,
    CAPTURE_PRINT_BATCH_SEC,
)

logger = logging.getLogger(__name__)

# Book updates arrive on every DOM change. Every book is kept up to
# CAPTURE_L2_MAX_HZ (a flood bound); a book over it is held, not dropped, and
# replaced by the next. Books reach the fenced worker in batches, like prints,
# so a fast runner's book cannot fill CAPTURE_PENDING_BATCHES and stop the
# recording (worker.submit treats a full backlog as data loss and finalizes).
BOOK_MIN_INTERVAL_SEC = 1.0 / CAPTURE_L2_MAX_HZ

_last_book_ts: dict[str, float] = {}
# Books IBKR sent that the recording will never write: a held book replaced by a newer one.
_books_coalesced: dict[str, int] = {}
# ... and how many of those the manifest has not been told about yet (ADR 031).
_books_unreported: dict[str, int] = {}
_pending_book: dict[str, dict] = {}
# Books waiting for their batch to be submitted: (ts, book, coalesced_before).
_pending_books: dict[str, list[tuple[float, dict, int]]] = {}
_last_book_submit: dict[str, float] = {}
# Prints buffered since the last submit, and when that submit was. Unlike the
# book, every buffered print is kept: a print is an event, not a snapshot.
_pending_prints: dict[str, list[dict]] = {}
_last_print_submit: dict[str, float] = {}
# What the last *recorded* book actually was, so health describes what
# reached disk rather than what some other module thinks is subscribed.
_observed_book: dict[str, dict] = {}


def reset_for_tests() -> None:
    _last_book_ts.clear()
    _books_coalesced.clear()
    _books_unreported.clear()
    _pending_book.clear()
    _pending_books.clear()
    _last_book_submit.clear()
    _observed_book.clear()
    _pending_prints.clear()
    _last_print_submit.clear()


def enqueue_print(payload) -> None:
    """Buffer one AllLast print and submit the batch when it is due.

    A fast tape delivers prints faster than the fenced worker drains them, and
    the backlog bound counts jobs, so one job per print made a runner's own
    volume stop its recording. Batching costs at most CAPTURE_PRINT_BATCH_SEC of
    write latency during a burst and nothing at all on a quiet tape, where the
    interval has always passed. A trailing partial batch is written by the next
    print or by ``flush_prints`` when the recording stops.
    """
    symbol = payload["symbol"]
    token = worker.session_token(symbol)
    if token is None:
        _pending_prints.pop(symbol, None)
        return
    batch = _pending_prints.setdefault(symbol, [])
    batch.append(dict(payload))
    now = time.time()
    last = _last_print_submit.get(symbol)
    if len(batch) < CAPTURE_PRINT_BATCH_MAX and last is not None and now - last < CAPTURE_PRINT_BATCH_SEC:
        return
    _submit_prints(symbol, token, now)


def _submit_prints(symbol: str, token: int, now: float) -> None:
    batch = _pending_prints.pop(symbol, None)
    if not batch:
        return
    _last_print_submit[symbol] = now
    if not worker.submit(_write_prints, batch, token=token):
        # Refused: the session is finalizing. Reopening the interval keeps the
        # next print from waiting on a submit time that never happened.
        _last_print_submit.pop(symbol, None)


def flush_prints(symbol: str) -> None:
    """Persist buffered prints. Call while the worker still accepts."""
    token = worker.session_token(symbol)
    if token is None:
        _pending_prints.pop(symbol, None)
        return
    _submit_prints(symbol, token, time.time())


def _write_prints(payloads: list[dict]) -> None:
    for payload in payloads:
        _write_print(payload)


def _write_print(payload: dict) -> None:
    from capture import bar_buckets, recorder
    from capture.schema import valid_timestamp
    from sale_conditions import row_sets_price

    if not valid_timestamp(payload.get("ts")):
        # Let the recorder diagnose it: converting here would raise inside the
        # worker and report a generic failure instead of invalid_timestamp_rows.
        recorder.record_print(payload)
        return
    payload["session_date"] = datetime.fromtimestamp(payload["ts"], ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    recorder.ensure_event_day(payload["symbol"], payload["ts"])
    if not recorder.record_print(payload):
        return
    # The row keeps every print; its bars take only prints that set a price.
    if not row_sets_price(payload):
        return
    bar_buckets.on_print(
        payload["symbol"],
        payload["ts"],
        payload["price"],
        payload["size"],
        source=payload["source"],
        session_date=payload["session_date"],
    )


def _tick9_close(symbol: str) -> float | None:
    """IBKR's tick-9 prior close on the symbol's live L1 line, when one is open (#542).

    Record holds the tape and depth lines, which carry no close; the scanner,
    HOD Momo or a Trader tab usually holds the L1 line. Read on the IB loop,
    where that line's ticker is written.
    """
    from ibkr import ticks

    close = getattr(ticks.get_ticker(symbol), "close", None)
    if isinstance(close, bool) or not isinstance(close, (int, float)):
        return None
    return float(close) if math.isfinite(close) and close > 0 else None


def enqueue_book(symbol: str, book: dict) -> None:
    """Depth / L1 snapshot -> capture quotes + l2. Enqueue only (ADR 010).

    IB's DOM rows carry no exchange timestamp, so receipt time is the honest
    event time for a book snapshot. The interval test also makes the stamp
    monotonic per symbol: a backward wall clock skips the row rather than
    tripping the recorder's timestamp-regression stop.

    A book inside the flood bound (``CAPTURE_L2_MAX_HZ``) is *held* rather than
    dropped, mirroring ``Fidelity.offer_l2``: the next book replaces it (the
    held one is counted lost, and the count rides on the next depth row to the
    manifest's ``l2_coalesced``), and ``flush_book`` writes it when the
    recording stops -- the last book before a lull is exactly the one worth
    having. Every other book joins its batch (ADR 031).
    """
    token = worker.session_token(symbol)
    if token is None:
        return
    if not (book.get("bids") or book.get("asks")):
        return  # Reserved/empty placeholder book -- nothing observed yet.
    # The quote row carries the prior close the replay's change is measured from.
    book = dict(book, prev_close=_tick9_close(symbol))
    ts = time.time()
    last = _last_book_ts.get(symbol)
    if last is not None and ts - last < BOOK_MIN_INTERVAL_SEC:
        if _pending_book.get(symbol) is not None:
            _lose_book(symbol)  # the held book is replaced before it was written
        _pending_book[symbol] = dict(book)
        return
    if _pending_book.pop(symbol, None) is not None:
        _lose_book(symbol)
    _last_book_ts[symbol] = ts
    _queue_book(symbol, token, ts, book)


def _lose_book(symbol: str) -> None:
    _books_coalesced[symbol] = _books_coalesced.get(symbol, 0) + 1
    _books_unreported[symbol] = _books_unreported.get(symbol, 0) + 1


def _queue_book(symbol: str, token: int, ts: float, book: dict) -> None:
    """Add a book to its batch; submit the batch when it is full or due."""
    held_back = 0
    if not book.get("l1_fallback"):
        # Only a depth book writes an l2 row, so only it can carry the count to the manifest.
        held_back = _books_unreported.pop(symbol, 0)
    batch = _pending_books.setdefault(symbol, [])
    batch.append((ts, dict(book), held_back))
    last = _last_book_submit.get(symbol)
    if len(batch) < CAPTURE_BOOK_BATCH_MAX and last is not None and ts - last < CAPTURE_BOOK_BATCH_SEC:
        return
    _submit_books(symbol, token, ts)


def _submit_books(symbol: str, token: int, now: float) -> None:
    batch = _pending_books.pop(symbol, None)
    if not batch:
        return
    _last_book_submit[symbol] = now
    if worker.submit(_write_books, symbol, batch, token=token):
        _mark_observed(symbol, batch[-1][1])
    else:
        # Refused: the session is finalizing. Reopening the interval keeps the
        # next book from waiting on a submit time that never happened.
        _last_book_submit.pop(symbol, None)
        _last_book_ts.pop(symbol, None)


def _write_books(symbol: str, batch: list[tuple[float, dict, int]]) -> None:
    for ts, book, held_back in batch:
        _write_book(symbol, ts, book, held_back=held_back)


def _mark_observed(symbol: str, book: dict) -> None:
    _observed_book[symbol] = {
        "levels": bool(book.get("bids") or book.get("asks")),
        "l1_fallback": bool(book.get("l1_fallback")),
    }


def flush_book(symbol: str) -> None:
    """Persist the batch and the newest held book. Call while the worker still accepts."""
    held = _pending_book.pop(symbol, None)
    token = worker.session_token(symbol)
    if token is None:
        _pending_books.pop(symbol, None)
        return
    if held is not None:
        ts = max(time.time(), _last_book_ts.get(symbol, 0) + BOOK_MIN_INTERVAL_SEC)
        _last_book_ts[symbol] = ts
        _queue_book(symbol, token, ts, held)
    _submit_books(symbol, token, time.time())


def _levels(rows) -> list[dict]:
    out: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict) or row.get("price") is None:
            continue
        out.append({"price": float(row["price"]), "size": float(row.get("size") or 0)})
    return out


def _write_book(symbol: str, ts: float, book: dict, *, held_back: int = 0) -> None:
    from capture.recorder import record_l2, record_quote

    day = datetime.fromtimestamp(ts, ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    bids, asks = _levels(book.get("bids")), _levels(book.get("asks"))
    record_quote(
        {
            "symbol": symbol,
            "ts": ts,
            "bid": bids[0]["price"] if bids else None,
            "bid_size": bids[0]["size"] if bids else None,
            "ask": asks[0]["price"] if asks else None,
            "ask_size": asks[0]["size"] if asks else None,
            "last": None,
            "volume": None,
            # IBKR tick 9 (#542): read first by the replay's previous close; null without an L1 line.
            "prev_close": book.get("prev_close"),
            "source": "ibkr",
            "session_date": day,
        }
    )
    # An L1 fallback book is top-of-book only -- recording it as depth would
    # claim a ladder the feed never delivered.
    if not book.get("l1_fallback"):
        record_l2(
            {
                "symbol": symbol,
                "ts": ts,
                "bids": bids,
                "asks": asks,
                "source": "ibkr",
                "session_date": day,
                # Popped by Fidelity.offer_l2 into l2_coalesced; never written to the row.
                "coalesced_before": held_back,
            }
        )


def book_health(symbol: str) -> dict:
    """Is the recorded symbol's book actually being captured, and as what.

    Keyed on an *observed* book, not on subscription membership: a reserved
    depth slot makes ``is_subscribed`` true while ``current_book`` is still the
    empty placeholder, which reported ``depth: true`` and suppressed the
    warning before a single row had been captured. A silent subscription reads
    the same way, and both are exactly the cases the operator needs told.
    """
    from ibkr.depth import state as depth_state

    subscribed = depth_state.is_subscribed(symbol)
    last = _observed_book.get(symbol)
    observed = last is not None
    has_levels = bool(last and last["levels"])
    l1_only = bool(last and last["l1_fallback"])
    if not subscribed:
        note = "No depth subscription for " + symbol + "; prints record but quotes and Level 2 do not"
    elif not observed:
        note = "No book received for " + symbol + " yet; quotes and Level 2 are not recording"
    else:
        note = None
    return {
        "subscribed": subscribed,
        "observed": observed,
        "depth": observed and has_levels and not l1_only,
        "l1_fallback": observed and l1_only,
        "last_book_ts": _last_book_ts.get(symbol),
        "books_coalesced": _books_coalesced.get(symbol, 0),
        "note": note,
    }


def producer_health(symbol: str) -> dict:
    """The recording's tape line. ``ended``: how IBKR ended it (``ibkr.tape_line``), else None."""
    from ibkr import client, tape_line, tape_stream
    from ibkr.tape_recording import producer_status

    state = producer_status(symbol)
    if not tape_stream.is_subscribed(symbol) or client.get_ib() is None:
        ended = tape_line.ended(symbol)
        error = ("IBKR ended the AllLast line for " + symbol + ": " + ended["message"] if ended
                 else "IBKR AllLast is not connected/subscribed for " + symbol)
        return state | {"state": "disconnected", "healthy": False, "error": error, "ended": ended}
    return state


def admission_error(symbol: str) -> str | None:
    return producer_health(symbol).get("error")
