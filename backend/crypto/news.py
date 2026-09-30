"""Crypto headlines for the Cryptos page (ADR 040): Alpaca's news for the listed coins over the last 24 hours.

Alpaca tags crypto articles with pair symbols (``BTCUSD``); each article is labelled by ``crypto/classify.py``
and filed under every listed coin it names. A coin Alpaca answered for with no article is "no news found"; a
coin never answered for is unknown -- the board keeps the difference (``news_checked``).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from constants_crypto import (
    CRYPTO_COINS,
    CRYPTO_NEWS_MAX_PAGES,
    CRYPTO_NEWS_PAGE_LIMIT,
    CRYPTO_NEWS_WINDOW_SEC,
)
from crypto.classify import classify_headline
from crypto.web import SourceError, get_json, num

SOURCE = "alpaca"
_BY_NEWS_SYMBOL = {c["news"]: c["symbol"] for c in CRYPTO_COINS}


def fetch_news(now: float | None = None) -> dict[str, list[dict]]:
    """``{coin symbol: [item]}`` for every listed coin (an empty list: Alpaca looked and found none)."""
    from alpaca import ALPACA_DATA_URL, _alpaca_headers

    headers = _alpaca_headers()
    if not headers:
        raise SourceError("no Alpaca keys in .env")
    now = time.time() if now is None else now
    articles: list[dict] = []
    token = None
    for _ in range(CRYPTO_NEWS_MAX_PAGES):
        params: dict[str, Any] = {"symbols": ",".join(_BY_NEWS_SYMBOL), "start": _iso(now - CRYPTO_NEWS_WINDOW_SEC),
                                  "end": _iso(now), "limit": CRYPTO_NEWS_PAGE_LIMIT, "sort": "desc",
                                  "include_content": "false"}
        if token:
            params["page_token"] = token
        body = get_json(f"{ALPACA_DATA_URL}/v1beta1/news", params=params, headers=headers)
        if not isinstance(body, dict) or not isinstance(body.get("news"), list):
            raise SourceError("Alpaca's news answer has no articles list")
        articles.extend(a for a in body["news"] if isinstance(a, dict))
        token = body.get("next_page_token")
        if not token:
            break
    return file_articles(articles)


def file_articles(articles: list[dict]) -> dict[str, list[dict]]:
    """Label each article once and file it under every listed coin it names, newest first."""
    out: dict[str, list[dict]] = {c["symbol"]: [] for c in CRYPTO_COINS}
    for art in articles:
        published = _parse_ts(art.get("created_at")) or _parse_ts(art.get("updated_at"))
        title = str(art.get("headline") or "").strip()
        if published is None or not title:
            continue
        tagged = [str(s).upper().replace("/", "") for s in art.get("symbols") or [] if s]
        coins = sorted({_BY_NEWS_SYMBOL[s] for s in tagged if s in _BY_NEWS_SYMBOL})
        if not coins:
            continue
        kind = classify_headline(title, str(art.get("summary") or ""), n_tickers=len(tagged))
        item = {"published_ts": published, "title": title, "kind": kind, "url": art.get("url") or None,
                "source": _source_name(art.get("source")), "coins": coins}
        for coin in coins:
            out[coin].append(item)
    for items in out.values():
        items.sort(key=lambda it: -it["published_ts"])
    return out


def _source_name(raw: Any) -> str:
    name = str(raw or "").strip()
    return name[:1].upper() + name[1:] if name else "Alpaca"


def _parse_ts(value: Any) -> float | None:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return num(value)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
