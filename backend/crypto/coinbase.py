"""Coinbase Exchange candles for the Cryptos page (ADR 040): the chart, and each 16:00 ET price the bridge uses.

``GET /products/{product}/candles?granularity=g[&start&end]`` answers at most 300 rows of ``[time, low, high,
open, close, volume]``, newest first, ``time`` the bucket's start in epoch seconds. Coinbase has no 4-hour
bucket, so 4h candles are built from hourly ones on UTC boundaries (00, 04, 08 ... UTC).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from constants_crypto import (
    CRYPTO_CANDLES_SHOWN,
    CRYPTO_COINBASE_BASE,
    CRYPTO_COINBASE_MAX_CANDLES,
    CRYPTO_COINBASE_PAGE_GAP_SEC,
)
from crypto.web import SourceError, get_json, num

SOURCE = "coinbase"
GRANULARITY = {"15m": 900, "1h": 3600, "1d": 86400}
FOUR_HOURS = 4 * 3600

Candle = dict  # {t, o, h, l, c, v}; v is None when Coinbase gave no volume


def parse_candles(body: Any) -> list[Candle]:
    """Coinbase rows -> candles oldest first, one per bucket; a malformed row is skipped."""
    if not isinstance(body, list):
        if isinstance(body, dict) and body.get("message"):
            raise SourceError(f"Coinbase: {str(body['message'])[:120]}")
        raise SourceError("Coinbase's candles answer is not a list")
    out: dict[int, Candle] = {}
    for row in body:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        t, low, high, open_, close, vol = (num(x) for x in row[:6])
        if None in (t, low, high, open_, close) or low > high:
            continue
        out[int(t)] = {"t": int(t), "o": open_, "h": high, "l": low, "c": close, "v": vol}
    return [out[t] for t in sorted(out)]


def fetch_page(product: str, granularity: int, start: float | None = None, end: float | None = None) -> list[Candle]:
    params: dict[str, Any] = {"granularity": granularity}
    if start is not None and end is not None:
        params["start"] = _iso(start)
        params["end"] = _iso(end)
    return parse_candles(get_json(f"{CRYPTO_COINBASE_BASE}/products/{product}/candles", params=params))


def fetch_history(product: str, granularity: int, seconds: float, now: float | None = None,
                  sleep: Callable[[float], None] = time.sleep) -> list[Candle]:
    """Every candle over the last ``seconds``, paged 300 at a time, oldest first."""
    now = time.time() if now is None else now
    # One bucket short of the cap: a window on bucket boundaries counts both ends, and Coinbase refuses a
    # range that would answer more than 300 rows.
    span = granularity * (CRYPTO_COINBASE_MAX_CANDLES - 1)
    end = now
    start_all = now - seconds
    pages: list[Candle] = []
    while end > start_all:
        start = max(start_all, end - span)
        pages.extend(fetch_page(product, granularity, start, end))
        end = start
        if end > start_all:
            sleep(CRYPTO_COINBASE_PAGE_GAP_SEC)
    return _dedupe(pages)


def fetch_series(product: str, tf: str, now: float | None = None) -> list[Candle]:
    """The chart's candles for ``tf``: the most recent ``CRYPTO_CANDLES_SHOWN`` of them."""
    if tf == "4h":
        hourly = fetch_history(product, GRANULARITY["1h"], (CRYPTO_CANDLES_SHOWN + 1) * FOUR_HOURS, now)
        return aggregate(hourly, FOUR_HOURS)[-CRYPTO_CANDLES_SHOWN:]
    if tf not in GRANULARITY:
        raise SourceError(f"no Coinbase granularity for {tf}")
    return fetch_page(product, GRANULARITY[tf])


def aggregate(candles: list[Candle], bucket: int) -> list[Candle]:
    """Candles folded into ``bucket``-second buckets on UTC boundaries (a partial last bucket kept)."""
    out: dict[int, Candle] = {}
    for c in candles:
        key = c["t"] - c["t"] % bucket
        cur = out.get(key)
        if cur is None:
            out[key] = {"t": key, "o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"], "v": c["v"]}
            continue
        cur["h"] = max(cur["h"], c["h"])
        cur["l"] = min(cur["l"], c["l"])
        cur["c"] = c["c"]
        # One hour of unknown volume makes the bucket's volume unknown, never a partial sum.
        cur["v"] = None if cur["v"] is None or c["v"] is None else cur["v"] + c["v"]
    return [out[t] for t in sorted(out)]


def price_at(candles: list[Candle], at: float, granularity: int) -> float | None:
    """The price at the instant ``at``: the open of the bucket that starts there, else the close of the one
    that ends there; ``None`` when neither is in the series (a gap is unknown, never interpolated)."""
    start = int(at)
    for c in candles:
        if c["t"] == start:
            return c["o"]
    for c in candles:
        if c["t"] + granularity == start:
            return c["c"]
    return None


def _dedupe(candles: list[Candle]) -> list[Candle]:
    seen: dict[int, Candle] = {}
    for c in candles:
        seen[c["t"]] = c
    return [seen[t] for t in sorted(seen)]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
