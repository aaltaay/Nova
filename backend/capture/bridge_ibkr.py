"""AllLast + depth feeder; all disk writes run on the existing fenced capture worker."""

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from capture import worker
from capture.constants_capture import CAPTURE_L2_MAX_HZ

logger = logging.getLogger(__name__)

# Book updates arrive on every DOM change -- far faster than the recorder
# coalesces (CAPTURE_L2_MAX_HZ) and far faster than the fenced worker drains.
# Coalescing here, before enqueue, keeps a fast runner's book from filling
# CAPTURE_PENDING_BATCHES and stopping the recording (worker.submit treats a
# full backlog as data loss and finalizes the session).
BOOK_MIN_INTERVAL_SEC = 1.0 / CAPTURE_L2_MAX_HZ

_last_book_ts: dict[str, float] = {}
_books_coalesced: dict[str, int] = {}


def reset_for_tests() -> None:
    _last_book_ts.clear()
    _books_coalesced.clear()


def enqueue_print(payload) -> None:
    token = worker.session_token(payload["symbol"])
    if token is not None:
        worker.submit(_write_print, dict(payload), token=token)


def _write_print(payload: dict) -> None:
    from capture import bar_buckets, recorder

    payload["session_date"] = datetime.fromtimestamp(payload["ts"], ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    recorder.ensure_event_day(payload["ts"])
    if not recorder.record_print(payload):
        return
    bar_buckets.on_print(
        payload["symbol"],
        payload["ts"],
        payload["price"],
        payload["size"],
        source=payload["source"],
        session_date=payload["session_date"],
    )


def enqueue_book(symbol: str, book: dict) -> None:
    """Depth / L1 snapshot -> capture quotes + l2. Enqueue only (ADR 010).

    IB's DOM rows carry no exchange timestamp, so receipt time is the honest
    event time for a book snapshot. The interval test also makes the stamp
    monotonic per symbol: a backward wall clock skips the row rather than
    tripping the recorder's timestamp-regression stop.
    """
    token = worker.session_token(symbol)
    if token is None:
        return
    if not (book.get("bids") or book.get("asks")):
        return  # Reserved/empty placeholder book -- nothing observed yet.
    ts = time.time()
    last = _last_book_ts.get(symbol)
    if last is not None and ts - last < BOOK_MIN_INTERVAL_SEC:
        _books_coalesced[symbol] = _books_coalesced.get(symbol, 0) + 1
        return
    _last_book_ts[symbol] = ts
    if not worker.submit(_write_book, symbol, ts, dict(book), token=token):
        _last_book_ts.pop(symbol, None)


def _levels(rows) -> list[dict]:
    out: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict) or row.get("price") is None:
            continue
        out.append({"price": float(row["price"]), "size": float(row.get("size") or 0)})
    return out


def _write_book(symbol: str, ts: float, book: dict) -> None:
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
            }
        )


def book_health(symbol: str) -> dict:
    """Is the recorded symbol's book actually being captured, and as what."""
    from ibkr import depth

    subscribed = depth.is_subscribed(symbol)
    book = depth.current_book(symbol) or {}
    l1_only = bool(book.get("l1_fallback"))
    return {
        "subscribed": subscribed,
        "depth": subscribed and not l1_only,
        "l1_fallback": subscribed and l1_only,
        "last_book_ts": _last_book_ts.get(symbol),
        "books_coalesced": _books_coalesced.get(symbol, 0),
        "note": (
            None
            if subscribed
            else "No depth subscription for " + symbol + "; prints record but quotes and Level 2 do not"
        ),
    }


def producer_health(symbol: str) -> dict:
    from ibkr import tape_stream
    from ibkr import client
    from ibkr.tape_recording import producer_status

    state = producer_status(symbol)
    if not tape_stream.is_subscribed(symbol) or client.get_ib() is None:
        return state | {
            "state": "disconnected",
            "healthy": False,
            "error": "IBKR AllLast is not connected/subscribed for " + symbol,
        }
    return state


def admission_error(symbol: str) -> str | None:
    from constants_sim import SIM_SYMBOL

    if symbol == SIM_SYMBOL:
        return None
    return producer_health(symbol).get("error")
