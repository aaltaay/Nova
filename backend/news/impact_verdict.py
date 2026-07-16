"""News impact verdict dataclass (ADR 004 strangler split)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from constants import NEWS_IMPACT_RULE_VERSION
from news.impact_helpers import factors_snapshot


@dataclass
class NewsImpactVerdict:
    symbol: str
    impact_class: str
    confidence: float
    age_hours: float | None
    age_bucket: str
    source_tier: str
    source_name: str | None
    confirmed_by_official: bool
    confirming_source_count: int
    price_reaction: str
    attention: str
    l2_reaction: str
    sentiment: str
    sentiment_score: float | None
    lexicon_sentiment: str
    lexicon_polarity: float | None
    headline: str | None
    headline_url: str | None
    summary: str
    reasons: list[str] = field(default_factory=list)
    factors: dict[str, Any] = field(default_factory=factors_snapshot)
    # Placeholder for Lincoln AI / later LLM narrative. None = not run yet.
    ai_reasoning: str | None = None
    rule_version: str = NEWS_IMPACT_RULE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
