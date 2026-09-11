"""Unify provider articles into desk stories and extract tickers."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from news.sources import classify_source_tier
from nova_news.criticality import score_story
from nova_news.models import ProviderResult, Story

_CASHTAG = re.compile(r"\$([A-Z]{1,5})\b")
_EXCHANGE_TICKER = re.compile(
    r"\b(?:NASDAQ|NYSE|AMEX|NYSEARCA):\s*([A-Z]{1,5})\b",
)
_FALSE_TICKERS = {
    "US", "CEO", "IPO", "FDA", "SEC", "ETF", "EV", "USD", "NYSE", "AMEX",
    "THE", "AND", "FOR", "NOT", "NEW",
}


def story_id(url: str, headline: str) -> str:
    raw = (url or headline).strip().lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def extract_symbols(article: dict) -> list[str]:
    found: list[str] = []
    raw = article.get("symbols")
    if isinstance(raw, list):
        found.extend(str(s).strip().upper() for s in raw if str(s).strip())
    elif isinstance(raw, str) and raw.strip():
        found.extend(part.strip().upper() for part in raw.split(",") if part.strip())

    text = f"{article.get('headline') or ''} {article.get('summary') or ''}"
    found.extend(_CASHTAG.findall(text))
    found.extend(_EXCHANGE_TICKER.findall(text))

    out: list[str] = []
    seen: set[str] = set()
    for sym in found:
        if not re.fullmatch(r"[A-Z]{1,5}", sym):
            continue
        if sym in _FALSE_TICKERS or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _outlet_kind(provider: str, source: str, tier: str) -> str:
    hay = f"{provider} {source}".lower()
    if "yahoo" in hay:
        return "yahoo"
    if tier == "official":
        return "official"
    if tier == "major":
        return "major"
    return "small"


def _tags(
    provider: str,
    source: str,
    tier: str,
    symbols: list[str],
    haystack: str,
    filing_hit: bool,
    macro_hit: bool,
) -> list[str]:
    tags: list[str] = []
    if "yahoo" in f"{provider} {source}".lower():
        tags.append("yahoo")
    if filing_hit or tier == "official":
        tags.append("filings")
    kind = _outlet_kind(provider, source, tier)
    if kind == "small":
        tags.append("small")
    if macro_hit or not symbols:
        tags.append("markets")
    return tags


def stories_from_providers(results: list[ProviderResult], now: datetime | None = None) -> list[Story]:
    by_id: dict[str, Story] = {}
    for result in results:
        if not result.ok:
            continue
        for article in result.articles:
            headline = str(article.get("headline") or "").strip()
            url = str(article.get("url") or "").strip()
            if not headline or not url:
                continue
            sid = story_id(url, headline)
            if sid in by_id:
                continue
            source = str(article.get("source") or result.label).strip() or result.label
            article = {**article, "source": source, "url": url, "headline": headline}
            symbols = extract_symbols(article)
            scored = score_story(article, now=now)
            story = Story(
                id=sid,
                headline=headline,
                summary=str(article.get("summary") or "").strip(),
                url=url,
                source=source,
                publisher=source,
                outlet_kind=_outlet_kind(result.id, source, scored.tier),
                criticality=scored.criticality,
                criticality_score=scored.score,
                reasons=scored.reasons,
                symbols=symbols,
                published_at=_iso(article.get("created_at")),
                age_hours=scored.age_hours,
                provider=result.id,
                tags=_tags(
                    result.id,
                    source,
                    scored.tier,
                    symbols,
                    scored.haystack,
                    scored.filing_hit,
                    scored.macro_hit,
                ),
            )
            by_id[sid] = story
    stories = list(by_id.values())
    stories.sort(
        key=lambda s: (s.criticality_score, s.published_at or ""),
        reverse=True,
    )
    return stories
