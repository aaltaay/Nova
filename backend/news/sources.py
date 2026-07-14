"""Explicit source-credibility tiers for news impact scoring.

Every keyword list is imported from constants.py — nothing is hidden.
Tiers (best → worst): official > major > secondary > unknown > none.
"""
from __future__ import annotations

from constants import (
    NEWS_IMPACT_MAJOR_SOURCE_KEYWORDS,
    NEWS_IMPACT_OFFICIAL_SOURCE_KEYWORDS,
    NEWS_IMPACT_OFFICIAL_URL_KEYWORDS,
    NEWS_IMPACT_SECONDARY_SOURCE_KEYWORDS,
)

# Ordered best-first for comparisons / max().
SOURCE_TIER_RANK = {
    "official": 4,
    "major": 3,
    "secondary": 2,
    "unknown": 1,
    "none": 0,
}


def _haystack(article: dict) -> str:
    parts = [
        str(article.get("source") or ""),
        str(article.get("author") or ""),
        str(article.get("url") or ""),
        str(article.get("headline") or ""),
    ]
    return " ".join(parts).lower()


def classify_source_tier(article: dict) -> str:
    """Return one of: official | major | secondary | unknown."""
    text = _haystack(article)
    if not text.strip():
        return "unknown"
    if any(k in text for k in NEWS_IMPACT_OFFICIAL_SOURCE_KEYWORDS):
        return "official"
    if any(k in text for k in NEWS_IMPACT_OFFICIAL_URL_KEYWORDS):
        return "official"
    if any(k in text for k in NEWS_IMPACT_MAJOR_SOURCE_KEYWORDS):
        return "major"
    if any(k in text for k in NEWS_IMPACT_SECONDARY_SOURCE_KEYWORDS):
        return "secondary"
    return "unknown"


def best_source_tier(articles: list[dict]) -> str:
    if not articles:
        return "none"
    return max(
        (classify_source_tier(a) for a in articles),
        key=lambda t: SOURCE_TIER_RANK.get(t, 0),
    )


def count_confirming_sources(articles: list[dict]) -> int:
    """Count distinct official/major sources (by normalized source string)."""
    seen: set[str] = set()
    for article in articles:
        tier = classify_source_tier(article)
        if tier not in ("official", "major"):
            continue
        key = (str(article.get("source") or article.get("url") or "").strip().lower())
        if key:
            seen.add(key)
    return len(seen)


def any_official(articles: list[dict]) -> bool:
    return any(classify_source_tier(a) == "official" for a in articles)


def best_source_name(articles: list[dict]) -> str | None:
    """Literal source string (e.g. 'Business Wire') of the best-tier article.

    Ties on tier break by most recent `created_at`. Returns None when there
    are no articles or the winning article has no source string.
    """
    if not articles:
        return None
    best = max(
        articles,
        key=lambda a: (SOURCE_TIER_RANK.get(classify_source_tier(a), 0), str(a.get("created_at") or "")),
    )
    name = str(best.get("source") or "").strip()
    return name or None
