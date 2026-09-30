"""CoinGecko for the Cryptos page (ADR 040): the coins' prices, changes, volumes and caps, and the whole market.

Three public endpoints: ``/coins/markets`` (every listed coin in one call, with its 7-day path), ``/global``
(total cap, volume, dominance) and ``/coins/{id}/market_chart`` (a coin's daily volumes, for its 30-day
average). A free demo key in ``COINGECKO_DEMO_API_KEY`` raises the rate limit; none is needed.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from constants_crypto import (
    CRYPTO_COINGECKO_BASE,
    CRYPTO_COINGECKO_KEY_ENV,
    CRYPTO_COINS,
    CRYPTO_SPARK_POINTS,
    CRYPTO_VOLUME_AVG_DAYS,
)
from crypto.web import SourceError, get_json, num

SOURCE = "coingecko"


def _headers() -> dict:
    key = (os.environ.get(CRYPTO_COINGECKO_KEY_ENV) or "").strip()
    return {"x-cg-demo-api-key": key} if key else {}


def fetch_markets() -> dict[str, dict]:
    ids = ",".join(c["coingecko"] for c in CRYPTO_COINS)
    body = get_json(f"{CRYPTO_COINGECKO_BASE}/coins/markets", headers=_headers(), params={
        "vs_currency": "usd", "ids": ids, "sparkline": "true", "price_change_percentage": "1h,24h,7d",
        "per_page": len(CRYPTO_COINS), "page": 1})
    return parse_markets(body)


def fetch_global() -> dict:
    return parse_global(get_json(f"{CRYPTO_COINGECKO_BASE}/global", headers=_headers()))


def fetch_volume_history(coin_id: str) -> list[float]:
    body = get_json(f"{CRYPTO_COINGECKO_BASE}/coins/{coin_id}/market_chart", headers=_headers(), params={
        "vs_currency": "usd", "days": CRYPTO_VOLUME_AVG_DAYS, "interval": "daily"})
    return parse_volume_history(body)


def parse_markets(body: Any) -> dict[str, dict]:
    """``/coins/markets`` rows -> ``{coin id: fields}``; a missing field is ``None``, never 0."""
    if not isinstance(body, list):
        raise SourceError("CoinGecko's markets answer is not a list")
    out: dict[str, dict] = {}
    for row in body:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        rank = num(row.get("market_cap_rank"))
        out[row["id"]] = {
            "price": num(row.get("current_price")),
            "rank": int(rank) if rank is not None else None,
            "high_24h": num(row.get("high_24h")),
            "low_24h": num(row.get("low_24h")),
            "change_1h_pct": num(row.get("price_change_percentage_1h_in_currency")),
            "change_24h_pct": _first(row.get("price_change_percentage_24h_in_currency"),
                                     row.get("price_change_percentage_24h")),
            "change_7d_pct": num(row.get("price_change_percentage_7d_in_currency")),
            "volume_24h_usd": num(row.get("total_volume")),
            "market_cap_usd": num(row.get("market_cap")),
            "market_cap_change_24h_usd": num(row.get("market_cap_change_24h")),
            "from_ath_pct": num(row.get("ath_change_percentage")),
            "spark_7d": _spark(row.get("sparkline_in_7d")),
            "updated_at": _iso_ts(row.get("last_updated")),
        }
    if not out:
        raise SourceError("CoinGecko's markets answer listed no coins")
    return out


def parse_global(body: Any) -> dict:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        raise SourceError("CoinGecko's global answer has no data")
    caps = data.get("total_market_cap") if isinstance(data.get("total_market_cap"), dict) else {}
    vols = data.get("total_volume") if isinstance(data.get("total_volume"), dict) else {}
    shares = data.get("market_cap_percentage") if isinstance(data.get("market_cap_percentage"), dict) else {}
    out = {
        "total_cap_usd": num(caps.get("usd")),
        "total_volume_usd": num(vols.get("usd")),
        "btc_dominance_pct": num(shares.get("btc")),
        "total_cap_change_24h_pct": num(data.get("market_cap_change_percentage_24h_usd")),
    }
    if out["total_cap_usd"] is None:
        raise SourceError("CoinGecko's global answer has no total market cap")
    return out


def parse_volume_history(body: Any) -> list[float]:
    """The completed days' 24-hour volumes, oldest first (the last point, the running day, left out)."""
    rows = body.get("total_volumes") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise SourceError("CoinGecko's market chart has no volumes")
    points = []
    for row in rows:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            ts, vol = num(row[0]), num(row[1])
            if ts is not None and vol is not None and vol > 0:
                points.append((ts, vol))
    points.sort()
    return [v for _, v in points[:-1]][-CRYPTO_VOLUME_AVG_DAYS:]


def _first(*values: Any) -> float | None:
    for value in values:
        out = num(value)
        if out is not None:
            return out
    return None


def _spark(block: Any) -> list[float]:
    prices = block.get("price") if isinstance(block, dict) else None
    if not isinstance(prices, list):
        return []
    clean = [p for p in (num(x) for x in prices) if p is not None]
    if len(clean) <= CRYPTO_SPARK_POINTS:
        return clean
    step = len(clean) / CRYPTO_SPARK_POINTS
    picked = [clean[int(i * step)] for i in range(CRYPTO_SPARK_POINTS - 1)]
    return picked + [clean[-1]]


def _iso_ts(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
