"""Native timestamp/last receipt metadata for diagnostics (#667), never pricing.

Owner: this adapter. A bounded identity map keeps each wrapper's ticker facts,
invalidated by a new IB instance, a new packet, eviction or receipt aging. No
request or disk write. The pinned Ticker has slots and no weak-reference support. String tick 45/88 is not in ticker.ticks.
"""
from __future__ import annotations

import logging
import math
import threading
from collections import OrderedDict
from typing import Any, Callable
from uuid import uuid4

from constants_perf import PERF_L1_TIMESTAMP_RECEIPT_MAX_AGE_SEC, PERF_L1_TIMESTAMP_SYMBOLS
from constants_tape import IBKR_LAST_TICK_TYPES

logger = logging.getLogger(__name__)
_INSTALLED = "_nova_timestamp_instance"
_metadata: OrderedDict[int, dict] = OrderedDict()
_lock = threading.Lock()


def epoch(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        val = float(raw.timestamp()) if hasattr(raw, "timestamp") else float(raw)
        if val > 1e12:
            val /= 1000
        return val if math.isfinite(val) and val > 1e9 else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _facts(ticker: Any) -> dict:
    with _lock:
        row = _metadata.get(id(ticker))
        if row is None or row["ticker"] is not ticker:
            return {}
        if row["session"] is not None and row["generation"] != row["session"]():
            return {}
        return dict(row)


def instance(ticker: Any) -> str | None:
    return _facts(ticker).get("instance")


def provenance(ticker: Any, arrival: float, *, seed: bool) -> dict:
    packet = epoch(getattr(ticker, "time", None))
    facts = _facts(ticker)
    native_price = (not seed and packet is not None and facts.get("price_packet") == packet
                    and 0 <= arrival - packet <= PERF_L1_TIMESTAMP_RECEIPT_MAX_AGE_SEC)
    receipt = facts.get("receipt")
    if receipt is not None:
        age = arrival - receipt["received_at"]
        if 0 <= age <= PERF_L1_TIMESTAMP_RECEIPT_MAX_AGE_SEC:
            receipt = {**receipt, "with_price": native_price and receipt["received_at"] == packet}
        else:
            receipt = None
    return {"instance": facts.get("instance"), "last_timestamp": epoch(getattr(ticker, "lastTimestamp", None)),
            "rt_time": epoch(getattr(ticker, "rtTime", None)), "native_price_received": native_price,
            "timestamp_receipt": receipt}


def install(ib: Any, *, session: Callable[[], int] | None = None) -> bool:
    """Idempotent per IB wrapper; keep native callbacks unchanged, tagging their own ticker."""
    wrapper = getattr(ib, "wrapper", None)
    if wrapper is None or not hasattr(wrapper, "subscriptions"):
        return False
    if getattr(wrapper, _INSTALLED, None) is not None:
        return True
    # The pinned ib_async decoder calls priceSizeTick; older wrappers used tickPrice.
    price_method = "priceSizeTick" if callable(getattr(wrapper, "priceSizeTick", None)) else "tickPrice"
    methods = {name: getattr(wrapper, name, None)
               for name in ("tickString", price_method, "tickByTickAllLast")}
    if not all(callable(fn) for fn in methods.values()):
        logger.warning("L1 timestamps: wrapper lacks native receipt callbacks; receipts stay unknown")
        return False
    token = uuid4().hex
    failed = False

    def tag(req_id: int, *, timestamp_type: int | None = None, price: bool = False) -> None:
        nonlocal failed
        try:
            ticker = wrapper.subscriptions.get_ticker(req_id)
            if ticker is None:
                return
            at = epoch(wrapper.lastTime)
            if at is None:
                return
            generation = session() if session is not None else None
            identity = f"{token}:{generation}"
            with _lock:
                key = id(ticker)
                facts = _metadata.get(key)
                if facts is None or facts["ticker"] is not ticker or facts["instance"] != identity:
                    facts = _metadata[key] = {"ticker": ticker, "instance": identity,
                                              "session": session, "generation": generation}
                _metadata.move_to_end(key)
                if len(_metadata) > PERF_L1_TIMESTAMP_SYMBOLS:
                    _metadata.popitem(last=False)
                    from perf import counters

                    counters.incr("l1_timestamp.receipt_discarded")
                if timestamp_type is not None:
                    field = "lastTimestamp" if timestamp_type == 45 else "delayedLastTimestamp"
                    facts["receipt"] = {"tick_type": timestamp_type,
                                        "stamp": epoch(getattr(ticker, field, None)), "received_at": at}
                if price:
                    facts["price_packet"] = at
        except Exception:
            if not failed:
                failed = True
                logger.warning("L1 timestamps: receipt metadata unavailable", exc_info=True)

    def tick_string(req_id, tick_type, value):
        methods["tickString"](req_id, tick_type, value)
        if tick_type in (45, 88):
            tag(req_id, timestamp_type=tick_type)

    def tick_price(req_id, tick_type, price, attrib):
        methods[price_method](req_id, tick_type, price, attrib)
        if tick_type in IBKR_LAST_TICK_TYPES:
            tag(req_id, price=True)

    def all_last(req_id, *args):
        methods["tickByTickAllLast"](req_id, *args)
        tag(req_id)

    wrapper.tickString = tick_string
    # Decoder.wrap captures the callback at IB construction. Price/AllLast
    # decode dynamically, but wire message 46 must capture our new hook.
    decoder = getattr(getattr(ib, "client", None), "decoder", None)
    if decoder is not None:
        try:
            if decoder.wrapper is not wrapper or 46 not in decoder.handlers:
                raise ValueError("Unexpected string-tick decoder")
            decoder.handlers[46] = decoder.wrap("tickString", [int, int, str])
        except Exception:
            wrapper.tickString = methods["tickString"]
            logger.warning("L1 timestamps: native decoder receipt hook unavailable", exc_info=True)
            return False
    setattr(wrapper, price_method, tick_price)
    wrapper.tickByTickAllLast = all_last
    setattr(wrapper, _INSTALLED, token)
    return True


def reset_for_tests() -> None:
    with _lock:
        _metadata.clear()
