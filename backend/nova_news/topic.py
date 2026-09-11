"""Admit only AI-in-trading headlines onto the Nova News desk.

The marketing digest (`tools/ai_news_rank.py`) taught the same lesson:
matching AI *or* markets floods the page with chatbot launches and index
moves. This module is the desk SSOT. Do not import `tools/`. Do not reuse
`rank_articles` -- that is a 6-item homepage shortlist, not a newsroom.
"""
from __future__ import annotations

import re

from constants import (
    NOVA_NEWS_AI_TERMS,
    NOVA_NEWS_BOUNDED_TERMS,
    NOVA_NEWS_FUND_KEYWORDS,
    NOVA_NEWS_HIGH_SIGNAL_PHRASES,
    NOVA_NEWS_MARKET_TERMS,
    NOVA_NEWS_RESEARCH_KEYWORDS,
)


def _contains(haystack: str, term: str) -> bool:
    if term in NOVA_NEWS_BOUNDED_TERMS:
        return re.search(rf"\b{re.escape(term)}\b", haystack) is not None
    return term in haystack


def count_terms(text: str, terms: tuple[str, ...]) -> int:
    """Distinct matching terms, not total occurrences."""
    return sum(1 for term in terms if _contains(text, term))


def first_hit(hay: str, keywords: tuple[str, ...]) -> str | None:
    for key in keywords:
        if _contains(hay, key):
            return key
    return None


def is_ai_trading_story(headline: str, summary: str = "") -> bool:
    """True only for "AI is used to trade" -- not "AI is a hot stock".

    Two independent ways to qualify:
    * a phrase that only appears when AI is doing the trading; or
    * the headline itself carries both an AI term and a trading term.
    """
    title = (headline or "").lower()
    body = f"{title} {(summary or '')}".lower()
    if count_terms(body, NOVA_NEWS_HIGH_SIGNAL_PHRASES) > 0:
        return True
    return (
        count_terms(title, NOVA_NEWS_AI_TERMS) > 0
        and count_terms(title, NOVA_NEWS_MARKET_TERMS) > 0
    )


def topic_tags(
    headline: str,
    summary: str = "",
    *,
    url: str = "",
    source: str = "",
) -> list[str]:
    title = (headline or "").lower()
    body = f"{title} {(summary or '')}".lower()
    hay = f"{body} {url} {source}".lower()
    tags: list[str] = []
    if count_terms(body, NOVA_NEWS_HIGH_SIGNAL_PHRASES) > 0:
        tags.append("executes")
    if count_terms(body, NOVA_NEWS_FUND_KEYWORDS) > 0:
        tags.append("funds")
    if count_terms(hay, NOVA_NEWS_RESEARCH_KEYWORDS) > 0 or "arxiv.org" in hay:
        tags.append("research")
    return tags
