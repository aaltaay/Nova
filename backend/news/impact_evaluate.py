"""News impact evaluation logic (ADR 004 strangler split)."""
from __future__ import annotations

from datetime import datetime

from constants import (
    NEWS_IMPACT_AGING_HOURS,
    NEWS_IMPACT_ATTENTION_RVOL,
    NEWS_IMPACT_FRESH_HOURS,
    NEWS_IMPACT_L2_IMBALANCE_MIN,
    NEWS_IMPACT_MILD_MOVE_PCT,
    NEWS_IMPACT_MULTI_SOURCE_CONFIRM,
    NEWS_IMPACT_STALE_HOURS,
    NEWS_IMPACT_STRONG_MOVE_PCT,
)
from news.ai_reasoning import generate_ai_reasoning
from news.impact_helpers import (
    age_bucket,
    age_hours,
    attention_state,
    clamp_confidence,
    factors_snapshot,
    gap_pct_points,
    l2_reaction,
    price_reaction,
)
from news.impact_verdict import NewsImpactVerdict
from news.lexicon import classify_headline_lexicon
from news.sentiment import classify_headline_sentiment
from news.sources import any_official, best_source_name, best_source_tier, count_confirming_sources


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
    factors = factors_snapshot()

    newest = newest_headline_at
    headline: str | None = None
    headline_url: str | None = None
    if articles:
        sorted_arts = sorted(
            articles,
            key=lambda a: str(a.get("created_at") or ""),
            reverse=True,
        )
        newest = newest or sorted_arts[0].get("created_at")
        headline = sorted_arts[0].get("headline") or sorted_arts[0].get("catalyst_headline")
        headline_url = sorted_arts[0].get("url") or sorted_arts[0].get("catalyst_url")

    age = age_hours(newest, now=now)
    bucket = age_bucket(age)
    tier = best_source_tier(articles)
    source_name = best_source_name(articles)
    confirm_count = count_confirming_sources(articles)
    official = any_official(articles) or confirm_count >= NEWS_IMPACT_MULTI_SOURCE_CONFIRM
    gap_pct = gap_pct_points(gap_percent)
    price = price_reaction(gap_pct)
    attention = attention_state(rel_volume)
    l2 = l2_reaction(l2_features)
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
    reasons.append(
        f"Best source tier is '{tier}'" + (f" ({source_name})." if source_name else ".")
    )
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
        confidence=clamp_confidence(confidence),
        age_hours=round(age, 3) if age is not None else None,
        age_bucket=bucket,
        source_tier=tier,
        source_name=source_name,
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
        headline_url=headline_url,
        summary=summary,
        reasons=reasons,
        factors=factors,
        ai_reasoning=ai_reasoning,
    )
