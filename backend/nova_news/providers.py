"""Fetch Nova News stories from HTTP APIs and public RSS feeds."""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import requests

from alpaca import ALPACA_DATA_URL, _alpaca_headers
from constants import (
    FINNHUB_MARKET_NEWS_URL,
    FINNHUB_NEWS_CATEGORIES,
    NEWS_CATALYST_ARTICLE_LIMIT,
    NEWS_CATALYST_LOOKBACK_HOURS,
    NOVA_NEWS_DESK_HTTP_TIMEOUT_SEC,
    NOVA_NEWS_HTTP_USER_AGENT,
    NOVA_NEWS_OUTLET_FEEDS,
    NOVA_NEWS_SEARCH_FEEDS,
)
from market import now_et
from nova_news.models import ProviderResult
from nova_news.rss import fetch_rss

logger = logging.getLogger(__name__)


def fetch_finnhub() -> ProviderResult:
    api_key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not api_key:
        return ProviderResult(
            id="finnhub",
            label="Finnhub",
            ok=False,
            count=0,
            error="FINNHUB_API_KEY is not set.",
        )
    articles: list[dict] = []
    last_error: str | None = None
    for category in FINNHUB_NEWS_CATEGORIES:
        try:
            resp = requests.get(
                FINNHUB_MARKET_NEWS_URL,
                params={"category": category, "token": api_key},
                timeout=NOVA_NEWS_DESK_HTTP_TIMEOUT_SEC,
                headers={"User-Agent": NOVA_NEWS_HTTP_USER_AGENT},
            )
        except Exception:
            logger.warning("nova_news: Finnhub %s failed", category, exc_info=True)
            last_error = "Finnhub request failed."
            continue
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After", "?")
            last_error = f"Finnhub rate-limited (Retry-After={retry})."
            logger.warning("nova_news: Finnhub 429 Retry-After=%s", retry)
            continue
        if resp.status_code != 200:
            last_error = f"Finnhub returned HTTP {resp.status_code}."
            continue
        try:
            payload = resp.json()
        except Exception:
            last_error = "Finnhub response was not JSON."
            continue
        if not isinstance(payload, list):
            continue
        for item in payload:
            headline = str(item.get("headline") or "").strip()
            url = str(item.get("url") or "").strip()
            if not headline or not url:
                continue
            created = item.get("datetime")
            created_at = None
            if isinstance(created, (int, float)) and created > 0:
                created_at = datetime_from_unix(created)
            articles.append({
                "headline": headline,
                "summary": str(item.get("summary") or ""),
                "url": url,
                "source": str(item.get("source") or "Finnhub"),
                "created_at": created_at,
                "symbols": str(item.get("related") or ""),
            })
    if not articles and last_error:
        return ProviderResult(
            id="finnhub", label="Finnhub", ok=False, count=0, error=last_error,
        )
    return ProviderResult(
        id="finnhub", label="Finnhub", ok=True, count=len(articles), articles=articles,
    )


def datetime_from_unix(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def fetch_alpaca() -> ProviderResult:
    headers = _alpaca_headers()
    if not headers:
        return ProviderResult(
            id="alpaca",
            label="Alpaca News",
            ok=False,
            count=0,
            error="Alpaca news keys are not set.",
        )
    lookback = (now_et() - timedelta(hours=NEWS_CATALYST_LOOKBACK_HOURS)).isoformat()
    try:
        resp = requests.get(
            f"{ALPACA_DATA_URL}/v1beta1/news",
            headers=headers,
            params={"start": lookback, "limit": NEWS_CATALYST_ARTICLE_LIMIT},
            timeout=NOVA_NEWS_DESK_HTTP_TIMEOUT_SEC,
        )
    except Exception:
        logger.warning("nova_news: Alpaca news failed", exc_info=True)
        return ProviderResult(
            id="alpaca", label="Alpaca News", ok=False, count=0,
            error="Alpaca news request failed.",
        )
    if resp.status_code != 200:
        return ProviderResult(
            id="alpaca", label="Alpaca News", ok=False, count=0,
            error=f"Alpaca news returned HTTP {resp.status_code}.",
        )
    try:
        payload = resp.json()
    except Exception:
        return ProviderResult(
            id="alpaca", label="Alpaca News", ok=False, count=0,
            error="Alpaca news response was not JSON.",
        )
    articles = []
    for item in payload.get("news") or []:
        headline = str(item.get("headline") or "").strip()
        url = str(item.get("url") or "").strip()
        if not headline or not url:
            continue
        articles.append({
            "headline": headline,
            "summary": str(item.get("summary") or ""),
            "url": url,
            "source": str(item.get("source") or "Alpaca"),
            "created_at": item.get("created_at"),
            "symbols": item.get("symbols") or [],
        })
    return ProviderResult(
        id="alpaca", label="Alpaca News", ok=True, count=len(articles), articles=articles,
    )


def fetch_all_providers() -> list[ProviderResult]:
    jobs = [fetch_finnhub, fetch_alpaca]
    for feed_id, label, url in (*NOVA_NEWS_SEARCH_FEEDS, *NOVA_NEWS_OUTLET_FEEDS):
        jobs.append(lambda fid=feed_id, lab=label, u=url: fetch_rss(fid, lab, u))

    results: list[ProviderResult] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(job) for job in jobs]
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception:
                logger.warning("nova_news: provider job crashed", exc_info=True)
    results.sort(key=lambda r: r.id)
    return results
