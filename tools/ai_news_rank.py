"""Ranking core for the AI-in-trading news digest on nova.altaystudio.com.

Pure functions only -- no network, no clock reads except the `now` passed in,
no file writes. `tools/ai_news_digest.py` owns fetching and rendering.

A story earns its slot on the homepage by clearing three independent bars:

1. Topic gate   -- the headline/summary must mention *both* an AI concept and a
                   markets concept. Union matching would flood the page with
                   generic chatbot launches and generic index moves.
2. Score        -- (topic depth + "AI is actually trading" bonus - promo noise)
                   scaled by source credibility and exponential recency decay.
3. Diversity    -- no single outlet may take more than MAX_PER_DOMAIN slots, so
                   one prolific feed cannot crowd out the rest.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from ai_news_sources import (
    BLOCKED_DOMAINS,
    FEED_SPAM_DOMAINS,
    REQUIRE_KNOWN_SOURCE,
    SOURCE_WEIGHTS,
    TRADE_PRESS_DOMAINS,
    UNKNOWN_CRYPTO_TERMS,
    UNKNOWN_SOURCE_WEIGHT,
)

# --- Tunables -------------------------------------------------------------
# "AI is actually trading" is a narrow beam -- some days produce two stories,
# not twenty. A 48h half-life over a 21-day window keeps the page full of real
# coverage instead of padding it with whatever was published this morning.
RECENCY_HALF_LIFE_HOURS = 72.0
MAX_AGE_DAYS = 21
# A headline hit says more about the story than a hit buried in the summary.
TITLE_WEIGHT = 3.0
SUMMARY_WEIGHT = 1.0
# Diminishing returns: the 6th synonym in one blurb is not new information.
MAX_TERM_HITS = 6
HIGH_SIGNAL_BONUS = 4.0
MAX_HIGH_SIGNAL_HITS = 3
NOISE_PENALTY = 3.5
MAX_PER_DOMAIN = 2
# Publish fewer stories rather than weak ones. A story this faded is either
# stale or barely on-topic; an empty slot is more honest than filler.
MIN_SCORE = 1.5
# Two headlines sharing this fraction of their words are the same wire story.
DUPLICATE_TITLE_OVERLAP = 0.6

# --- Vocabulary -----------------------------------------------------------
AI_TERMS = (
    "artificial intelligence", "machine learning", "deep learning",
    "neural network", "large language model", "generative ai", "genai",
    "reinforcement learning", "foundation model", "transformer model",
    "ai model", "ai system", "ai tool", "ai agent", "agentic", "chatgpt",
    "openai", "anthropic", "deepmind", "llm", "algorithm", "ai",
)

# Deliberately narrow: these describe *the act of trading or running money*.
# Loose finance words ("exchange", "investor", "fund", "alpha") were tried and
# removed -- they turned "Claude exchanges" and a "Seeking Alpha" byline into
# false positives and flooded the page with AI-as-a-hot-stock coverage.
MARKET_TERMS = (
    "trading", "trader", "trade", "trades", "trade desk", "trading desk",
    "hedge fund", "quant", "quantitative", "asset manager",
    "asset management", "portfolio", "market maker", "market making",
    "broker", "brokerage", "order flow", "order execution",
    "trade execution", "backtest", "buy-side", "sell-side", "buy side",
    "proprietary trading", "wealth management", "stock picking",
    "securities trading", "high-frequency", "market microstructure",
    "invest", "invests", "investing", "investment",
    "wall street", "capital markets", "stock market",
    "equities", "fund manager", "money manager",
)
# "investor"/"investors" are absent on purpose: as nouns they overwhelmingly
# describe venture backers ("Anthropic Investor Leads Funding"), not someone
# trading. The verb forms above still catch "AI Agents Invest His Money".
# Bare "market", "exchange", "fund", and "alpha" are deliberately absent: each
# one turned AI-company business coverage into false "AI trades" hits.

# The crown jewels: phrases that mean AI is *doing the trading*, not merely
# being traded as a theme. These are what the user asked to surface.
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
# Rejected from the list above, with reasons, so they do not creep back:
#   "ai fund"            -> matched "Google's AI Fund" (venture capital)
#   "machine learning model" / "predictive model"
#                        -> generic ML; carries no trading meaning on its own

# Retail clickbait and promo copy. Real, but never "best of the best".
NOISE_PHRASES = (
    "stocks to buy", "best ai stocks", "best ai trading", "top 5", "top 10", "top 3",
    "should you buy", "should buy", "price prediction", "price target",
    "motley fool", "sponsored", "prnewswire", "globenewswire", "giveaway",
    "discount", "here's why", "here's where", "millionaire", "get rich",
    "penny stock", "analysts see", "share price", "buy both", "buy now",
    "growth stock", "billionaire", "if you invested", "my top",
    "annualized return", "guaranteed", "webinar", "press release",
    # Capex and venture funding. "Google to Invest $15B in AI Infrastructure"
    # is money moving *into* AI, not AI moving money -- the opposite of the
    # beat. Penalized rather than banned so a genuinely strong trading story
    # that happens to mention a raise can still win on its own merits.
    "funding", "venture capital", "series a", "series b", "series c",
    "raises $", "valuation", "invest $", "ai infrastructure", "data center",
    "data centre", "startup", "led the round", "ipo", "capex",
    "chipmaker", "semiconductor",
)

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")
# Short/ambiguous terms need word boundaries so "sec" does not match "second"
# and "llm" does not match inside a longer token.
_BOUNDED_TERMS = frozenset({
    "ai", "llm", "genai", "quant", "trade", "trades", "broker",
    # "invest" unbounded matches "investigation"; the family is listed explicitly.
    "invest", "invests", "investing", "investment",
})
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "as", "at", "by", "from", "that", "this", "it", "its",
    "how", "why", "what", "new", "says", "say", "will", "be",
})


@dataclass
class Article:
    """One candidate story. `source` is the feed's human label."""

    title: str
    url: str
    summary: str = ""
    source: str = ""
    published: datetime | None = None
    # Aggregators (Google News) link through a redirect. The publisher is the
    # thing whose credibility we are actually judging, so keep it separate.
    publisher_url: str = ""
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    @property
    def domain(self) -> str:
        return domain_of(self.publisher_url or self.url)


def domain_of(url: str) -> str:
    """Registrable-ish host, lowercased, without `www.`."""
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def canonical_url(url: str) -> str:
    """Drop tracking query/fragment so the same story dedupes across feeds."""
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, parts.netloc.lower(), path, "", ""))


def _contains(haystack: str, term: str) -> bool:
    if term in _BOUNDED_TERMS:
        return re.search(rf"\b{re.escape(term)}\b", haystack) is not None
    return term in haystack


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    """Distinct matching terms, not total occurrences."""
    return sum(1 for term in terms if _contains(text, term))


def _lookup_weight(url: str) -> float | None:
    """Allowlist hit for this URL, matching parents (`news.x.com` -> `x.com`)."""
    host = domain_of(url)
    if host in BLOCKED_DOMAINS:
        return None
    while host:
        if host in SOURCE_WEIGHTS:
            return SOURCE_WEIGHTS[host]
        _, _, host = host.partition(".")
    return None


def source_weight(url: str) -> float:
    """Credibility multiplier; unlisted domains fall back to the low default."""
    weight = _lookup_weight(url)
    return UNKNOWN_SOURCE_WEIGHT if weight is None else weight


def _host_in(url: str, table: frozenset[str]) -> bool:
    host = domain_of(url)
    while host:
        if host in table:
            return True
        _, _, host = host.partition(".")
    return False


def is_blocked_source(url: str) -> bool:
    """True for press-release hosts, including when unknown sources are allowed."""
    return _host_in(url, BLOCKED_DOMAINS)


def is_spam_source(url: str) -> bool:
    """True for exchange blogs and content mills that sneak past the topic gate."""
    return _host_in(url, FEED_SPAM_DOMAINS)


def is_known_source(url: str) -> bool:
    return _lookup_weight(url) is not None


def recency_factor(published: datetime | None, now: datetime) -> float:
    """Exponential decay in [0, 1]. Undated stories are treated as one half-life old."""
    if published is None:
        return 0.5
    age_hours = (now - published).total_seconds() / 3600.0
    if age_hours < 0:  # feed clock skew / scheduled posts
        age_hours = 0.0
    if age_hours > MAX_AGE_DAYS * 24:
        return 0.0
    return math.pow(0.5, age_hours / RECENCY_HALF_LIFE_HOURS)


def is_on_topic(article: Article) -> bool:
    """True only for "AI is used to trade" -- not "AI is a hot stock".

    Two independent ways to qualify:
      * the story names a phrase that only appears when AI is doing the
        trading ("algorithmic trading", "quant fund", "execution algorithm"); or
      * the *headline itself* carries both an AI term and a trading term, which
        means the pairing is the subject of the piece, not an aside.

    Matching AI and markets anywhere in the blurb was tried first and failed:
    it ranked "Wall Street Analysts See Nvidia's Share Price Going" as a top
    story about AI trading.
    """
    title = article.title.lower()
    body = f"{title} {article.summary}".lower()
    if _count_terms(body, HIGH_SIGNAL_PHRASES) > 0:
        return True
    return _count_terms(title, AI_TERMS) > 0 and _count_terms(title, MARKET_TERMS) > 0


def score_article(article: Article, now: datetime) -> float:
    """Score a single story and record why, for auditability."""
    title = article.title.lower()
    summary = article.summary.lower()
    reasons: list[str] = []

    ai_depth = min(
        TITLE_WEIGHT * _count_terms(title, AI_TERMS)
        + SUMMARY_WEIGHT * _count_terms(summary, AI_TERMS),
        MAX_TERM_HITS * TITLE_WEIGHT,
    )
    market_depth = min(
        TITLE_WEIGHT * _count_terms(title, MARKET_TERMS)
        + SUMMARY_WEIGHT * _count_terms(summary, MARKET_TERMS),
        MAX_TERM_HITS * TITLE_WEIGHT,
    )
    topic = ai_depth + market_depth

    high_signal = min(
        _count_terms(f"{title} {summary}", HIGH_SIGNAL_PHRASES),
        MAX_HIGH_SIGNAL_HITS,
    )
    if high_signal:
        reasons.append(f"{high_signal} AI-executes-trades phrase(s)")

    noise = _count_terms(f"{title} {summary}", NOISE_PHRASES)
    if noise:
        reasons.append(f"-{noise} promo phrase(s)")

    raw = topic + HIGH_SIGNAL_BONUS * high_signal - NOISE_PENALTY * noise
    if raw <= 0:
        article.reasons = reasons
        return 0.0

    weight = source_weight(article.publisher_url or article.url)
    decay = recency_factor(article.published, now)
    reasons.append(f"source x{weight:g}")
    reasons.append(f"recency x{decay:.2f}")

    article.reasons = reasons
    return raw * weight * decay


def _title_tokens(title: str) -> frozenset[str]:
    return frozenset(
        token for token in _WORD_SPLIT.split(title.lower())
        if token and token not in _STOPWORDS and len(token) > 2
    )


def _is_duplicate(tokens: frozenset[str], seen: list[frozenset[str]]) -> bool:
    """Same wire story rewritten: high word overlap against an already-kept title."""
    if not tokens:
        return False
    for other in seen:
        if not other:
            continue
        overlap = len(tokens & other) / min(len(tokens), len(other))
        if overlap >= DUPLICATE_TITLE_OVERLAP:
            return True
    return False


def rank_articles(
    articles: list[Article],
    now: datetime,
    limit: int,
    *,
    max_per_domain: int | None = None,
    min_score: float | None = None,
    require_known_source: bool | None = None,
    trade_press_boost: float = 1.0,
) -> list[Article]:
    """Filter, score, dedupe, and diversify down to `limit` stories.

    Homepage keeps the tight defaults (2 per domain, known sources only).
    The public /news feed passes a higher domain cap and a trade-press boost
    so small publishers can fill 50+ rows without becoming a CNBC clone.
    """
    scored: list[Article] = []
    seen_urls: set[str] = set()
    known_gate = REQUIRE_KNOWN_SOURCE if require_known_source is None else require_known_source
    floor = MIN_SCORE if min_score is None else min_score
    domain_cap = MAX_PER_DOMAIN if max_per_domain is None else max_per_domain

    for article in articles:
        if not article.title.strip() or not article.url.strip():
            continue
        key = canonical_url(article.url)
        if key in seen_urls:
            continue
        url = article.publisher_url or article.url
        if is_blocked_source(url) or is_spam_source(url):
            continue
        known = is_known_source(url)
        if known_gate and not known:
            continue
        if not is_on_topic(article):
            continue
        if not known:
            body = f"{article.title} {article.summary}".lower()
            if _count_terms(body, UNKNOWN_CRYPTO_TERMS) > 0:
                continue
        article.score = score_article(article, now)
        if trade_press_boost != 1.0 and article.domain in TRADE_PRESS_DOMAINS:
            article.score *= trade_press_boost
        if article.score < floor:
            continue
        seen_urls.add(key)
        scored.append(article)

    scored.sort(key=lambda a: a.score, reverse=True)

    picked: list[Article] = []
    seen_titles: list[frozenset[str]] = []
    per_domain: dict[str, int] = {}
    for article in scored:
        if len(picked) >= limit:
            break
        tokens = _title_tokens(article.title)
        if _is_duplicate(tokens, seen_titles):
            continue
        domain = article.domain
        if per_domain.get(domain, 0) >= domain_cap:
            continue
        per_domain[domain] = per_domain.get(domain, 0) + 1
        seen_titles.append(tokens)
        picked.append(article)

    return picked
