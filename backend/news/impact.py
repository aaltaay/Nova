"""Rules-first news → ticker / Level 2 impact verdict.

Strangler facade (ADR 004). Implementation lives in:
  news.impact_helpers, news.impact_verdict, news.impact_evaluate.

Every threshold comes from constants.py. Every outcome carries human-readable
`reasons[]`. `sentiment` comes from a local FinBERT model (news.sentiment),
`lexicon_sentiment` from the Loughran-McDonald financial word list
(news.lexicon), and `ai_reasoning` from an opt-in LLM call
(news.ai_reasoning) — all three are informational narrative layered on top;
the rules remain the visible, authoritative decision layer and are never
overridden by any of them.

Facade owner: Pattern-Driven Architecture (news slice).
Removal criterion: no production imports of this facade for helpers that
live in ``news.impact_*``; migrate callers to the focused modules.
"""
from __future__ import annotations

from news.impact_evaluate import evaluate_news_impact
from news.impact_helpers import (
    AGE_BUCKETS,
    ATTENTION_STATES,
    IMPACT_CLASSES,
    L2_REACTIONS,
    PRICE_REACTIONS,
)
from news.impact_verdict import NewsImpactVerdict

__all__ = [
    "AGE_BUCKETS",
    "ATTENTION_STATES",
    "IMPACT_CLASSES",
    "L2_REACTIONS",
    "NewsImpactVerdict",
    "PRICE_REACTIONS",
    "evaluate_news_impact",
]
