"""Normalize AllLast once, preserving provenance before isolated recording dispatch."""

from __future__ import annotations
import logging
import math
import time
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any
from ibkr.tape_exchange_time import exchange_second
from ibkr.tape_side import best_bid_ask, classify_print_side
from metrics.op_metrics import timed_fn
from sale_conditions import sets_price

logger = logging.getLogger(__name__)


def _clean(x: float | None) -> float | None:
    if x is None:
        return None
    try:
        return float(x) if math.isfinite(float(x)) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _practice_desk() -> bool:
    """A Sim desk off the live edge: viewers read the replay, never the market."""
    from sim.mode import is_replay_desk
    return is_replay_desk()


@timed_fn("ib.tape")
def on_tape_update(ticker: Any, symbol: str, push, depth) -> None:
    """Called on every updateEvent for the tick-by-tick ticker."""
    tbt_list = getattr(ticker, "tickByTicks", None)
    if not tbt_list:
        return
    for tbt in tbt_list:
        ts = getattr(tbt, "time", None)
        # ib_async stamps every tick with its arrival at Nova (Wrapper.lastTime),
        # never IBKR's own time, so ``ts`` is an arrival time and says so (#563).
        # IBKR's whole second rides beside it as ``exchange_ts`` when
        # ``tape_exchange_time`` caught it; prints stay in arrival order, like the books.
        ts_source = "receive"
        exchange_ts = exchange_second(tbt)
        if ts is None:
            ts_iso = datetime.now(timezone.utc).isoformat()
        elif hasattr(ts, "isoformat"):
            ts_iso = ts.isoformat()
        else:
            ts_iso = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()

        price = _clean(getattr(tbt, "price", None))
        size = _clean(getattr(tbt, "size", None))
        # IB sends sentinel empties; skip non-positive prices.
        if price is None or price <= 0 or size is None or size <= 0:
            continue

        exchange = getattr(tbt, "exchange", None) or ""
        conditions = getattr(tbt, "specialConditions", None) or ""
        # Reported for volume only (odd lot, average price, ...): Time & Sales
        # shows it, no candle takes it (sale_conditions.py).
        unreported = bool(getattr(getattr(tbt, "tickAttribLast", None), "unreported", False))
        price_ok = sets_price(conditions, unreported=unreported)

        # Classify against the open symbol's live BBO (depth / L1). Never use
        # another symbol's book — current_book is keyed by the tape symbol.
        bid, ask = best_bid_ask(depth.current_book(symbol))
        side = classify_print_side(price, bid, ask)

        size_i = int(size) if size is not None else 0
        payload = {
            "type": "print",
            "symbol": symbol,
            "time": ts_iso,
            "price": price,
            "size": size_i,
            "exchange": exchange,
            "conditions": conditions,
            "unreported": unreported,
            "sets_price": price_ok,
            "side": side,
            "bid": bid,
            "ask": ask,
            "ts": datetime.fromisoformat(ts_iso).timestamp(),
            "receive_ts": time.time(),
            "ts_source": ts_source,
            "exchange_ts": exchange_ts,
            "source": "ibkr",
        }
        from ibkr.tape_recording import dispatch

        dispatch(MappingProxyType(dict(payload)))
        try:
            from book_watch.live import enqueue_print

            enqueue_print(payload)  # the book watcher's tape (ADR 033); enqueue only
        except Exception:
            logger.exception("IBKR tape: book watcher enqueue failed for %s", symbol)
        # On a Sim desk off the live edge the only live line is one Session
        # Record holds (#315): it feeds the recording above, but the practice
        # desk's viewers and sensors read the replay through these same queues
        # and must not see the market. At the edge the tab is live and does.
        if not _practice_desk():
            push(symbol, dict(payload))
        # P6 — durable local archive (non-fatal if archive package fails).
        # ADR 010: this runs inside the ib_async socket callback, so it must
        # only enqueue. A synchronous SQLite write here starved reqMktData for
        # the whole desk on high-print runners (2026-08-18 IB-loop wedge).
        try:
            from archive.write_queue import enqueue_tape_print
            from constants import ARCHIVE_SOURCE_IBKR

            print_ts = payload["ts"]
            enqueue_tape_print(
                symbol=symbol,
                ts=print_ts,
                price=price,
                size=float(size_i),
                exchange=exchange,
                conditions=conditions,
                side=side,
                bid=bid,
                ask=ask,
                receive_ts=payload["receive_ts"],
                source=ARCHIVE_SOURCE_IBKR,
            )
            if not price_ok:
                continue
            # 1m OHLCV for archive/replay (same IBKR tape source — not Alpaca).
            from archive.bar_builder import on_tape_print

            on_tape_print(
                symbol=symbol,
                ts=print_ts,
                price=price,
                size=float(size_i),
                source=ARCHIVE_SOURCE_IBKR,
                queued=True,
            )
            # Provisional 10Sec chart bars (D-003 / ADR 012) -- paints the
            # Trader 10Sec pane in seconds instead of waiting on the paced
            # 4h IB historical fill. Hist fill still lands and replaces.
            from ibkr import tape_10sec as _tape_10sec

            _tape_10sec.on_print(symbol, price, float(size_i), print_ts)
        except Exception:
            logger.exception("IBKR tape: archive enqueue failed for %s", symbol)

    # Clear consumed ticks to avoid re-processing on next updateEvent
    try:
        tbt_list.clear()
    except (AttributeError, TypeError) as exc:
        logger.debug("IBKR tape: could not clear tick list for %s: %s", symbol, exc)


def warm_10sec_fill(symbol: str) -> None:
    """First Trader tape subscriber for a symbol warms its 10Sec hist fill
    (D-003) -- ``priority="warm"`` sheds on any pacing wait, so this never
    competes with a genuinely empty pane's ``open_chart`` fill."""
    try:
        if not _should_warm_10sec(symbol):
            return
        from constants import IBKR_10SEC_FETCH_BARS
        from ibkr.historical_service import schedule_fill

        schedule_fill(symbol, "10Sec", IBKR_10SEC_FETCH_BARS, priority="warm")
    except Exception:
        logger.debug("IBKR tape: 10Sec warm schedule failed for %s", symbol, exc_info=True)


def _should_warm_10sec(symbol: str) -> bool:
    """Mirrors the store-settled guard ``routes/ticker.py`` uses for its warm
    timeframes -- true when the store is missing, incomplete, or stale."""
    import bars_store
    from constants import IBKR_10SEC_FETCH_BARS

    stored = bars_store.read(symbol, "10Sec", IBKR_10SEC_FETCH_BARS)
    if not stored or not stored.get("bars"):
        return True
    if not bars_store.store_series_complete("10Sec", len(stored["bars"])):
        return True
    return not bars_store.is_coverage_fresh(stored.get("coverage"), "10Sec")
