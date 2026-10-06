"""Bounded timestamp evidence and nearby AllLast candidates (#667).

Owner: this module queues/reads evidence; PerfStore writes its separately
capped l1_timestamps/<ET-day>.jsonl with perf retention. Schema 1; unknown
versions refuse. All correlation runs on the perf evidence worker, off both
loops. IB callbacks only offer bounded primitive facts. A new IB instance
cannot correlate with an old instance, and old arrival facts age out.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Callable, Any

from constants_perf import (
    PERF_ENV_SWITCH, PERF_L1_TIMESTAMP_CANDIDATES, PERF_L1_TIMESTAMP_MATCH_SEC,
    PERF_L1_TIMESTAMP_PRICE_QUEUE, PERF_L1_TIMESTAMP_PRICES_PER_SEC,
    PERF_L1_TIMESTAMP_PRINTS_PER_SEC, PERF_L1_TIMESTAMP_PRINTS_PER_SYMBOL,
    PERF_L1_TIMESTAMP_SCHEMA_VERSION, PERF_L1_TIMESTAMP_SYMBOLS,
    PERF_L1_TIMESTAMP_TAPE_QUEUE, PERF_L1_TIMESTAMP_WAIT_SEC,
)
from perf import counters

_prices: queue.Queue = queue.Queue(maxsize=PERF_L1_TIMESTAMP_PRICE_QUEUE)
_prints: queue.Queue = queue.Queue(maxsize=PERF_L1_TIMESTAMP_TAPE_QUEUE)
_pending: deque = deque()
_tape: OrderedDict = OrderedDict()
_rate_lock = threading.Lock()
_rates: dict[str, tuple[int, int]] = {}
_flush_lock = threading.Lock()


def enabled() -> bool:
    return os.environ.get(PERF_ENV_SWITCH, "1").strip().lower() not in ("0", "false", "off", "no")


def _offer(kind: str, obj: dict, inbox: queue.Queue, limit: int) -> None:
    second = int(time.monotonic())
    with _rate_lock:
        prior, count = _rates.get(kind, (second, 0))
        count = count if prior == second else 0
        if count >= limit:
            counters.incr("l1_timestamp.rate_dropped")
            return
        _rates[kind] = (second, count + 1)
    try:
        inbox.put_nowait(obj)
    except queue.Full:
        counters.incr("l1_timestamp.queue_dropped")


def note_price(symbol: str, price: float, price_ts: float, arrival_ts: float, *,
               metadata: dict, seed: bool, quote_quality: str | None) -> None:
    if not enabled():
        return
    _offer("price", {"schema_version": PERF_L1_TIMESTAMP_SCHEMA_VERSION, "kind": "l1_timestamp",
                     "symbol": symbol, "price": price, "price_ts": price_ts, "arrival_ts": arrival_ts,
                     "seed": seed, "quote_quality": quote_quality, **metadata},
           _prices, PERF_L1_TIMESTAMP_PRICES_PER_SEC)


def note_tape(symbol: str, price: float, exchange_ts: int | None, arrival_ts: float, *,
              instance: str | None, price_ok: bool) -> None:
    if not enabled() or not price_ok or instance is None:
        return
    _offer("tape", {"symbol": symbol, "instance": instance, "price": price,
                    "exchange_ts": exchange_ts, "arrival_ts": arrival_ts},
           _prints, PERF_L1_TIMESTAMP_PRINTS_PER_SEC)


def _take(inbox: queue.Queue) -> list[dict]:
    # Bound one drain even while the IB thread keeps producing.
    out = []
    for _ in range(inbox.maxsize):
        try:
            out.append(inbox.get_nowait())
        except queue.Empty:
            break
    return out


def flush(persist: Callable[[dict], Any], *, now: float | None = None) -> None:
    """Run on one worker thread, delayed so a following tape print can be a candidate too."""
    now = time.time() if now is None else now
    with _flush_lock:
        for row in _take(_prints):
            key = (row["instance"], row["symbol"])
            ring = _tape.setdefault(key, deque(maxlen=PERF_L1_TIMESTAMP_PRINTS_PER_SYMBOL))
            if len(ring) == ring.maxlen:
                counters.incr("l1_timestamp.tape_discarded")
            ring.append(row)
            _tape.move_to_end(key)
            if len(_tape) > PERF_L1_TIMESTAMP_SYMBOLS:
                _tape.popitem(last=False)
                counters.incr("l1_timestamp.tape_discarded")
        for row in _take(_prices):
            if len(_pending) >= PERF_L1_TIMESTAMP_PRICE_QUEUE:
                _pending.popleft()
                counters.incr("l1_timestamp.queue_dropped")
            _pending.append(row)
        for _ in range(len(_pending)):
            row = _pending.popleft()
            if now - row["arrival_ts"] < PERF_L1_TIMESTAMP_WAIT_SEC:
                _pending.append(row)
                continue
            candidates = []
            for print_row in _tape.get((row["instance"], row["symbol"]), ()):
                delta = print_row["arrival_ts"] - row["arrival_ts"]
                if abs(delta) <= PERF_L1_TIMESTAMP_MATCH_SEC and print_row["price"] == row["price"]:
                    candidates.append({k: print_row[k] for k in ("price", "exchange_ts", "arrival_ts")}
                                      | {"delta_sec": round(delta, 6)})
            row["tape_candidates"] = candidates[:PERF_L1_TIMESTAMP_CANDIDATES]
            row["candidates_truncated"] = len(candidates) > PERF_L1_TIMESTAMP_CANDIDATES
            if persist(row) is False:
                counters.incr("l1_timestamp.queue_dropped")
        cutoff = now - PERF_L1_TIMESTAMP_WAIT_SEC - PERF_L1_TIMESTAMP_MATCH_SEC
        for key, ring in list(_tape.items()):
            while ring and ring[0]["arrival_ts"] < cutoff:
                ring.popleft()
            if not ring:
                _tape.pop(key)


def read_file(path: Path):
    """Read diagnostic rows; an unknown schema never masquerades as current evidence."""
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            if row.get("schema_version") != PERF_L1_TIMESTAMP_SCHEMA_VERSION:
                raise ValueError("Unsupported L1 timestamp evidence schema")
            yield row


def reset_for_tests() -> None:
    with _flush_lock:
        _take(_prices)
        _take(_prints)
        _pending.clear()
        _tape.clear()
    with _rate_lock:
        _rates.clear()
