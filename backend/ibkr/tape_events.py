"""Normalize AllLast once, preserving provenance before isolated recording dispatch."""

from __future__ import annotations
import logging
import math
import time
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any
from ibkr.tape_side import best_bid_ask, classify_print_side

logger = logging.getLogger(__name__)


def _clean(x: float | None) -> float | None:
    if x is None:
        return None
    try:
        return float(x) if math.isfinite(float(x)) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _practice_desk() -> bool:
    from sim.mode import is_sim_mode
    return is_sim_mode()


def on_tape_update(ticker: Any, symbol: str, push, depth) -> None:
    """Called on every updateEvent for the tick-by-tick ticker."""
    tbt_list = getattr(ticker, "tickByTicks", None)
    if not tbt_list:
        return
    for tbt in tbt_list:
        ts = getattr(tbt, "time", None)
        # A print with no exchange time is stamped on arrival; say so, so a
        # recording never presents a substituted time as the exchange's own.
        ts_source = "exchange" if ts is not None else "receive"
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
            "side": side,
            "bid": bid,
            "ask": ask,
            "ts": datetime.fromisoformat(ts_iso).timestamp(),
            "receive_ts": time.time(),
            "ts_source": ts_source,
            "source": "ibkr",
        }
        from ibkr.tape_recording import dispatch

        dispatch(MappingProxyType(dict(payload)))
        # On a Sim desk the only live line is one Session Record holds (#315): it
        # feeds the recording above, but the practice desk's viewers and sensors
        # read the replay through these same queues and must not see the market.
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
