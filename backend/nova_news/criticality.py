"""Rules-first criticality scoring for Nova News stories.

No FinBERT. Thresholds live in constants_archive_news.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from constants import (
    NOVA_NEWS_CRITICAL_KEYWORDS,
    NOVA_NEWS_CRITICAL_MIN_SCORE,
    NOVA_NEWS_FILING_KEYWORDS,
    NOVA_NEWS_HIGH_KEYWORDS,
    NOVA_NEWS_HIGH_MIN_SCORE,
    NOVA_NEWS_MACRO_KEYWORDS,
    NOVA_NEWS_TIER_POINTS,
    NOVA_NEWS_WATCH_MIN_SCORE,
)
from news.impact_helpers import age_hours
from news.sources import classify_source_tier


@dataclass(frozen=True)
class CriticalityScore:
    criticality: str
    score: int
    reasons: list[str]
    tier: str
    age_hours: float | None
    haystack: str
    filing_hit: bool
    macro_hit: bool


def _haystack(article: dict) -> str:
    return " ".join([
        str(article.get("headline") or ""),
        str(article.get("summary") or ""),
        str(article.get("source") or ""),
    ]).lower()


def _first_hit(hay: str, keywords: tuple[str, ...]) -> str | None:
    for key in keywords:
        if key in hay:
            return key
    return None


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
    hay = _haystack(article)
    tier = classify_source_tier(article)
    points = int(NOVA_NEWS_TIER_POINTS.get(tier, 0))
    reasons = [f"Source tier {tier}."]

    crit = _first_hit(hay, NOVA_NEWS_CRITICAL_KEYWORDS)
    high = _first_hit(hay, NOVA_NEWS_HIGH_KEYWORDS)
    filing = _first_hit(hay, NOVA_NEWS_FILING_KEYWORDS)
    macro = _first_hit(hay, NOVA_NEWS_MACRO_KEYWORDS)

    if crit:
        points += 40
        reasons.append(f"Critical language: {crit}.")
    elif high:
        points += 22
        reasons.append(f"High-signal language: {high}.")

    if filing or tier == "official":
        points += 10
        reasons.append("Official / filing language.")

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
        filing_hit=bool(filing),
        macro_hit=bool(macro),
    )
