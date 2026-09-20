"""Topic gate for the marketing-site AI-in-trading digest.

Pure functions. Scoring and diversity live in `ai_news_rank.py`.
"""
from __future__ import annotations

import re

from ai_news_sources import STRICT_MARKET_TERMS, THEME_REJECT_PHRASES, TRADE_PRESS_DOMAINS

AI_TERMS = (
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "large language model", "generative ai", "genai",
    "reinforcement learning", "foundation model", "transformer model",
    "ai model", "ai system", "ai tool", "ai agent", "agentic", "chatgpt",
    "openai", "anthropic", "deepmind", "llm", "algorithm", "ai",
    "claude", "gemini",
)

MARKET_TERMS = STRICT_MARKET_TERMS + (
    "invest", "invests", "investing", "investment",
    "wall street", "stock market",
)

HIGH_SIGNAL_PHRASES = (
    "algorithmic trading", "algo trading", "ai trading", "ai-powered trading",
    "ai-driven trading", "trading algorithm", "trading bot", "trading model",
    "quantitative trading", "systematic trading", "high-frequency trading",
    "quant fund", "quant hedge fund", "ai hedge fund",
    "execution algorithm", "alpha generation", "signal generation",
    "portfolio optimization", "robo-advisor", "robo-adviser",
    "market microstructure", "ai analyst", "autonomous trading",
    "trading strategy", "ai in markets", "ai brokered", "brokered trade",
)

NOISE_PHRASES = (
    "stocks to buy", "best ai stocks", "best ai trading", "top 5", "top 10", "top 3",
    "should you buy", "should buy", "price prediction", "price target",
    "motley fool", "sponsored", "prnewswire", "globenewswire", "giveaway",
    "discount", "here's why", "here's where", "millionaire", "get rich",
    "penny stock", "analysts see", "share price", "buy both", "buy now",
    "growth stock", "billionaire", "if you invested", "my top",
    "annualized return", "guaranteed", "webinar", "press release",
    "funding", "venture capital", "series a", "series b", "series c",
    "raises $", "valuation", "invest $", "ai infrastructure", "data center",
    "data centre", "startup", "led the round", "ipo", "capex",
    "chipmaker", "semiconductor",
)

_BOUNDED_TERMS = frozenset({
    "ai", "llm", "genai", "quant", "trade", "trades", "broker",
    "invest", "invests", "investing", "investment",
    "agent", "agents", "bot", "bots",
})


def contains(haystack: str, term: str) -> bool:
    if term in _BOUNDED_TERMS:
        return re.search(rf"\b{re.escape(term)}\b", haystack) is not None
    return term in haystack


def count_terms(text: str, terms: tuple[str, ...]) -> int:
    """Distinct matching terms, not total occurrences."""
    return sum(1 for term in terms if contains(text, term))


def is_theme_reject(article) -> bool:
    """True for AI-as-a-stock, banker tooling, and review-farm filler."""
    hay = f"{article.title} {article.summary}".lower()
    return any(phrase in hay for phrase in THEME_REJECT_PHRASES)


def is_on_topic(article) -> bool:
    """True only for "AI is used to trade" -- not "AI is a hot stock".

    Theme rejects fire first. Then a doing-the-trading phrase, or the
    headline pairs AI with a strict markets term. "AI agents invest his
    money" still qualifies through the agent/bot exception.
    """
    if is_theme_reject(article):
        return False
    title = article.title.lower()
    body = f"{title} {article.summary}".lower()
    if count_terms(body, HIGH_SIGNAL_PHRASES) > 0:
        return True
    if count_terms(title, AI_TERMS) == 0:
        return False
    if count_terms(title, STRICT_MARKET_TERMS) > 0:
        return True
    invest_hit = count_terms(title, ("invest", "invests", "investing", "investment")) > 0
    agent_hit = count_terms(title, ("agent", "agents", "bot", "bots", "algorithm")) > 0
    if invest_hit and agent_hit:
        return True
    # Trade press often puts the AI word in the hed and the desk word in the
    # blurb, or the other way around. Title-only pairing dropped those rows.
    if article.domain in TRADE_PRESS_DOMAINS:
        return (
            count_terms(body, AI_TERMS) > 0
            and count_terms(body, STRICT_MARKET_TERMS) > 0
        )
    return False
