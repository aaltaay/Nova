"""Rules-first news → ticker / Level 2 impact verdict.

Every threshold comes from constants.py. Every outcome carries human-readable
`reasons[]`. `sentiment` comes from a local FinBERT model (news.sentiment),
`lexicon_sentiment` from the Loughran-McDonald financial word list
(news.lexicon), and `ai_reasoning` from an opt-in LLM call
(news.ai_reasoning) — all three are informational narrative layered on top;
the rules remain the visible, authoritative decision layer and are never
overridden by any of them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from constants import (
    NEWS_IMPACT_AGING_HOURS,
    NEWS_IMPACT_ATTENTION_RVOL,
    NEWS_IMPACT_CONFIDENCE_CEILING,
    NEWS_IMPACT_CONFIDENCE_FLOOR,
    NEWS_IMPACT_FRESH_HOURS,
    NEWS_IMPACT_L2_IMBALANCE_MIN,
    NEWS_IMPACT_MILD_MOVE_PCT,
    NEWS_IMPACT_MULTI_SOURCE_CONFIRM,
    NEWS_IMPACT_RULE_VERSION,
    NEWS_IMPACT_STALE_HOURS,
    NEWS_IMPACT_STRONG_MOVE_PCT,
)
from news.ai_reasoning import generate_ai_reasoning
from news.lexicon import classify_headline_lexicon
from news.sentiment import classify_headline_sentiment
from news.sources import any_official, best_source_tier, count_confirming_sources

IMPACT_CLASSES = ("moved_price", "attention_only", "no_effect", "insufficient_data")
AGE_BUCKETS = ("fresh", "aging", "stale", "expired", "unknown")
PRICE_REACTIONS = ("strong", "mild", "flat", "unknown")
L2_REACTIONS = ("reacting", "quiet", "insufficient_data")
ATTENTION_STATES = ("elevated", "normal", "unknown")


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _age_hours(newest_at: str | None, now: datetime | None = None) -> float | None:
    published = _parse_iso(newest_at)
    if published is None:
        return None
    now = now or datetime.now(timezone.utc)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return max(0.0, (now - published).total_seconds() / 3600.0)


def _age_bucket(age_hours: float | None) -> str:
    if age_hours is None:
        return "unknown"
    if age_hours <= NEWS_IMPACT_FRESH_HOURS:
        return "fresh"
    if age_hours <= NEWS_IMPACT_AGING_HOURS:
        return "aging"
    if age_hours <= NEWS_IMPACT_STALE_HOURS:
        return "stale"
    return "expired"


def _gap_pct_points(gap_percent: float | None) -> float | None:
    """Normalize gap to percentage points. Accepts fraction (0.12) or points (12)."""
    if gap_percent is None:
        return None
    try:
        raw = float(gap_percent)
    except (TypeError, ValueError):
        return None
    # Heuristic: values with |x| ≤ 1.5 are treated as fractions (150% max as fraction).
    if abs(raw) <= 1.5:
        return abs(raw) * 100.0
    return abs(raw)


def _price_reaction(gap_pct: float | None) -> str:
    if gap_pct is None:
        return "unknown"
    if gap_pct >= NEWS_IMPACT_STRONG_MOVE_PCT:
        return "strong"
    if gap_pct >= NEWS_IMPACT_MILD_MOVE_PCT:
        return "mild"
    return "flat"


def _attention_state(rel_volume: float | None) -> str:
    if rel_volume is None:
        return "unknown"
    try:
        return "elevated" if float(rel_volume) >= NEWS_IMPACT_ATTENTION_RVOL else "normal"
    except (TypeError, ValueError):
        return "unknown"


def _l2_reaction(l2_features: dict | None) -> str:
    if not l2_features:
        return "insufficient_data"
    if l2_features.get("bid_heavy") is True:
        return "reacting"
    imb = l2_features.get("imbalance")
    try:
        if imb is not None and abs(float(imb)) >= NEWS_IMPACT_L2_IMBALANCE_MIN:
            return "reacting"
    except (TypeError, ValueError):
        pass
    # Explicit quiet only when we actually computed features.
    if "imbalance" in l2_features or "bid_heavy" in l2_features:
        return "quiet"
    return "insufficient_data"


def _clamp_confidence(raw: float) -> float:
    return round(
        max(NEWS_IMPACT_CONFIDENCE_FLOOR, min(NEWS_IMPACT_CONFIDENCE_CEILING, raw)),
        3,
    )


def _factors_snapshot() -> dict[str, Any]:
    """Expose every tunable used by this rule version (UI / debugging)."""
    return {
        "rule_version": NEWS_IMPACT_RULE_VERSION,
        "fresh_hours": NEWS_IMPACT_FRESH_HOURS,
        "aging_hours": NEWS_IMPACT_AGING_HOURS,
        "stale_hours": NEWS_IMPACT_STALE_HOURS,
        "strong_move_pct": NEWS_IMPACT_STRONG_MOVE_PCT,
        "mild_move_pct": NEWS_IMPACT_MILD_MOVE_PCT,
        "attention_rvol": NEWS_IMPACT_ATTENTION_RVOL,
        "l2_imbalance_min": NEWS_IMPACT_L2_IMBALANCE_MIN,
        "multi_source_confirm": NEWS_IMPACT_MULTI_SOURCE_CONFIRM,
        "confidence_floor": NEWS_IMPACT_CONFIDENCE_FLOOR,
        "confidence_ceiling": NEWS_IMPACT_CONFIDENCE_CEILING,
    }


@dataclass
class NewsImpactVerdict:
    symbol: str
    impact_class: str
    confidence: float
    age_hours: float | None
    age_bucket: str
    source_tier: str
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
    summary: str
    reasons: list[str] = field(default_factory=list)
    factors: dict[str, Any] = field(default_factory=_factors_snapshot)
    # Placeholder for Lincoln AI / later LLM narrative. None = not run yet.
    ai_reasoning: str | None = None
    rule_version: str = NEWS_IMPACT_RULE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_news_impact(
    symbol: str,
    articles: list[dict] | None,
    *,
    gap_percent: float | None = None,
    rel_volume: float | None = None,
    l2_features: dict | None = None,
    newest_headline_at: str | None = None,
    now: datetime | None = None,
) -> NewsImpactVerdict:
    """Classify whether news appears to affect the ticker / Level 2.

    Decision tree (plain English — also mirrored in reasons[]):
      1. No articles → insufficient_data.
      2. Expired news + any price move → no_effect (too old to attribute).
      3. Fresh/aging + strong/mild price move → moved_price (bump due to news).
      4. Fresh/aging + flat price + elevated RVOL → attention_only.
      5. Fresh/aging + flat price + normal/unknown RVOL → no_effect.
      6. Otherwise → insufficient_data.
    """
    articles = list(articles or [])
    reasons: list[str] = []
    factors = _factors_snapshot()

    newest = newest_headline_at
    headline: str | None = None
    if articles:
        sorted_arts = sorted(
            articles,
            key=lambda a: str(a.get("created_at") or ""),
            reverse=True,
        )
        newest = newest or sorted_arts[0].get("created_at")
        headline = sorted_arts[0].get("headline") or sorted_arts[0].get("catalyst_headline")

    age = _age_hours(newest, now=now)
    bucket = _age_bucket(age)
    tier = best_source_tier(articles)
    confirm_count = count_confirming_sources(articles)
    official = any_official(articles) or confirm_count >= NEWS_IMPACT_MULTI_SOURCE_CONFIRM
    gap_pct = _gap_pct_points(gap_percent)
    price = _price_reaction(gap_pct)
    attention = _attention_state(rel_volume)
    l2 = _l2_reaction(l2_features)
    sentiment_result = classify_headline_sentiment(headline)
    lexicon_result = classify_headline_lexicon(headline)

    factors["observed"] = {
        "article_count": len(articles),
        "age_hours": round(age, 3) if age is not None else None,
        "gap_pct_points": round(gap_pct, 3) if gap_pct is not None else None,
        "rel_volume": rel_volume,
        "l2_imbalance": (l2_features or {}).get("imbalance"),
        "l2_bid_heavy": (l2_features or {}).get("bid_heavy"),
        "sentiment": sentiment_result["label"],
        "sentiment_score": sentiment_result["score"],
        "lexicon_sentiment": lexicon_result["label"],
        "lexicon_polarity": lexicon_result["polarity"],
    }

    # --- Visible factor narration ---
    if not articles:
        reasons.append("No news articles available for this symbol.")
    else:
        reasons.append(f"{len(articles)} article(s) considered; newest age bucket is '{bucket}'.")
        if age is not None:
            reasons.append(
                f"Newest headline is {age:.2f}h old "
                f"(fresh≤{NEWS_IMPACT_FRESH_HOURS}h, aging≤{NEWS_IMPACT_AGING_HOURS}h, "
                f"stale≤{NEWS_IMPACT_STALE_HOURS}h)."
            )
    reasons.append(f"Best source tier is '{tier}'.")
    if official:
        reasons.append(
            f"Confirmed by official/major sources "
            f"(official={any_official(articles)}, confirming_count={confirm_count}, "
            f"need≥{NEWS_IMPACT_MULTI_SOURCE_CONFIRM})."
        )
    else:
        reasons.append(
            f"Not confirmed by official websites/wires "
            f"(confirming_count={confirm_count}, need≥{NEWS_IMPACT_MULTI_SOURCE_CONFIRM})."
        )
    if gap_pct is not None:
        reasons.append(
            f"Price reaction '{price}' from |gap|={gap_pct:.2f}% "
            f"(strong≥{NEWS_IMPACT_STRONG_MOVE_PCT}%, mild≥{NEWS_IMPACT_MILD_MOVE_PCT}%)."
        )
    else:
        reasons.append("Price reaction unknown — no gap/change percent provided.")
    if rel_volume is not None:
        reasons.append(
            f"Attention '{attention}' from RVOL={float(rel_volume):.2f} "
            f"(elevated≥{NEWS_IMPACT_ATTENTION_RVOL})."
        )
    else:
        reasons.append("Attention unknown — no relative volume provided.")
    if l2 == "reacting":
        reasons.append(
            f"Level 2 appears to be reacting "
            f"(imbalance threshold |x|≥{NEWS_IMPACT_L2_IMBALANCE_MIN} or bid-heavy)."
        )
    elif l2 == "quiet":
        reasons.append("Level 2 book is available but not showing a reaction signal.")
    else:
        reasons.append("Level 2 reaction insufficient_data — no book features available.")
    if sentiment_result["label"] == "unavailable":
        reasons.append("FinBERT headline sentiment unavailable (model not loaded or no headline text).")
    else:
        reasons.append(
            f"FinBERT headline sentiment is '{sentiment_result['label']}' "
            f"(score={sentiment_result['score']}) — informational only, does not change impact_class."
        )
    if lexicon_result["label"] == "unavailable":
        reasons.append("Loughran-McDonald lexicon sentiment unavailable (dependency missing or no headline text).")
    else:
        reasons.append(
            f"Loughran-McDonald lexicon sentiment is '{lexicon_result['label']}' "
            f"(polarity={lexicon_result['polarity']}) — informational only, does not change impact_class."
        )

    # --- Classification ---
    impact = "insufficient_data"
    confidence = 0.2
    summary = "Not enough data to judge news impact."

    if not articles:
        impact = "insufficient_data"
        confidence = 0.2
        summary = "No news to evaluate."
    elif bucket == "expired":
        impact = "no_effect"
        confidence = 0.7 if price in ("strong", "mild") else 0.55
        summary = (
            "News is too old to attribute the current move to it."
            if price in ("strong", "mild")
            else "News is expired and shows no attributable effect."
        )
        reasons.append(
            "Rule: age_bucket=expired → impact_class=no_effect "
            "(cannot credit this headline for a current bump)."
        )
    elif bucket in ("fresh", "aging") and price in ("strong", "mild"):
        impact = "moved_price"
        confidence = 0.55
        if price == "strong":
            confidence += 0.15
        if bucket == "fresh":
            confidence += 0.1
        if tier in ("official", "major"):
            confidence += 0.1
        if official:
            confidence += 0.05
        if l2 == "reacting":
            confidence += 0.05
        summary = "Bump appears due to news (price moved while headline is still fresh/aging)."
        reasons.append(
            "Rule: fresh/aging news + strong/mild price move → impact_class=moved_price."
        )
    elif bucket in ("fresh", "aging", "stale") and price == "flat" and attention == "elevated":
        impact = "attention_only"
        confidence = 0.5 + (0.1 if bucket == "fresh" else 0.0)
        summary = "News drew attention (elevated RVOL) without a meaningful price move."
        reasons.append(
            "Rule: news present + flat price + elevated RVOL → impact_class=attention_only."
        )
    elif bucket in ("fresh", "aging", "stale") and price == "flat":
        impact = "no_effect"
        confidence = 0.55 if attention == "normal" else 0.4
        summary = "News did not meaningfully affect the ticker (price flat)."
        reasons.append(
            "Rule: news present + flat price + no attention spike → impact_class=no_effect."
        )
    elif bucket == "stale" and price in ("strong", "mild"):
        # Stale but not expired: weak attribution.
        impact = "moved_price"
        confidence = 0.35
        if tier in ("official", "major"):
            confidence += 0.1
        summary = "Possible news-related move, but the headline is stale — attribution is weak."
        reasons.append(
            "Rule: stale news + price move → impact_class=moved_price at low confidence."
        )
    else:
        impact = "insufficient_data"
        confidence = 0.25
        summary = "Mixed or incomplete signals — cannot classify news impact yet."
        reasons.append("Rule: fallthrough → impact_class=insufficient_data.")

    if not articles:
        ai_reasoning = None
        reasons.append("Lincoln AI reasoning skipped — no articles to interpret.")
    else:
        ai_reasoning = generate_ai_reasoning(symbol, headline, summary, sentiment_result)
        if ai_reasoning:
            reasons.append("Lincoln AI reasoning generated from the headline and rules-based verdict.")
        else:
            reasons.append(
                "Lincoln AI reasoning unavailable (disabled by default — set LINCOLN_AI_ENABLED=true "
                "and OPENAI_API_KEY to enable, or the LLM call failed)."
            )

    return NewsImpactVerdict(
        symbol=symbol.upper(),
        impact_class=impact,
        confidence=_clamp_confidence(confidence),
        age_hours=round(age, 3) if age is not None else None,
        age_bucket=bucket,
        source_tier=tier,
        confirmed_by_official=bool(official),
        confirming_source_count=confirm_count,
        price_reaction=price,
        attention=attention,
        l2_reaction=l2,
        sentiment=sentiment_result["label"],
        sentiment_score=sentiment_result["score"],
        lexicon_sentiment=lexicon_result["label"],
        lexicon_polarity=lexicon_result["polarity"],
        headline=headline,
        summary=summary,
        reasons=reasons,
        factors=factors,
        ai_reasoning=ai_reasoning,
    )
