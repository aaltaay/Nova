"""Rules-first criticality for AI-in-trading stories.

No FinBERT. Thresholds live in constants_archive_news.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from constants import (
    NOVA_NEWS_CRITICAL_MIN_SCORE,
    NOVA_NEWS_HIGH_MIN_SCORE,
    NOVA_NEWS_HIGH_SIGNAL_PHRASES,
    NOVA_NEWS_NOISE_PHRASES,
    NOVA_NEWS_REGULATORY_KEYWORDS,
    NOVA_NEWS_TIER_POINTS,
    NOVA_NEWS_WATCH_MIN_SCORE,
)
from news.impact_helpers import age_hours
from news.sources import classify_source_tier
from nova_news.topic import first_hit, is_ai_trading_story, topic_tags


@dataclass(frozen=True)
class CriticalityScore:
    criticality: str
    score: int
    reasons: list[str]
    tier: str
    age_hours: float | None
    haystack: str
    topic_tags: list[str]


def _haystack(article: dict) -> str:
    return " ".join([
        str(article.get("headline") or ""),
        str(article.get("summary") or ""),
        str(article.get("source") or ""),
    ]).lower()


def _band(score: int) -> str:
    if score >= NOVA_NEWS_CRITICAL_MIN_SCORE:
        return "critical"
    if score >= NOVA_NEWS_HIGH_MIN_SCORE:
        return "high"
    if score >= NOVA_NEWS_WATCH_MIN_SCORE:
        return "watch"
    return "background"


def score_story(article: dict, *, now: datetime | None = None) -> CriticalityScore:
    now = now or datetime.now(timezone.utc)
    headline = str(article.get("headline") or "")
    summary = str(article.get("summary") or "")
    hay = _haystack(article)
    tier = classify_source_tier(article)
    points = int(NOVA_NEWS_TIER_POINTS.get(tier, 0))
    reasons = [f"Source tier {tier}."]
    tags = topic_tags(
        headline,
        summary,
        url=str(article.get("url") or ""),
        source=str(article.get("source") or ""),
    )

    high_signal = first_hit(hay, NOVA_NEWS_HIGH_SIGNAL_PHRASES)
    if high_signal:
        points += 40
        reasons.append(f"AI is doing the trading: {high_signal}.")
    elif is_ai_trading_story(headline, summary):
        points += 22
        reasons.append("Headline pairs AI with trading.")

    if "funds" in tags and high_signal:
        points += 8
        reasons.append("Fund / desk coverage.")
    if "research" in tags:
        points += 6
        reasons.append("Primary research.")

    regulatory = first_hit(hay, NOVA_NEWS_REGULATORY_KEYWORDS)
    if regulatory:
        points += 12
        reasons.append(f"Regulatory language: {regulatory}.")

    noise = first_hit(hay, NOVA_NEWS_NOISE_PHRASES)
    if noise:
        points -= 25
        reasons.append(f"Promo / stock-tip language: {noise}.")

    age = age_hours(article.get("created_at"), now=now)
    if age is not None:
        if age <= 2:
            points += 15
            reasons.append("Fresh under 2 hours.")
        elif age <= 6:
            points += 8
            reasons.append("Aging under 6 hours.")
        elif age > 24:
            points -= 20
            reasons.append("Older than 24 hours.")

    score = max(0, min(100, points))
    return CriticalityScore(
        criticality=_band(score),
        score=score,
        reasons=reasons,
        tier=tier,
        age_hours=round(age, 3) if age is not None else None,
        haystack=hay,
        topic_tags=tags,
    )
