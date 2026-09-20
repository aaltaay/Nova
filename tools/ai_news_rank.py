"""Ranking core for the AI-in-trading news digest on nova.altaystudio.com.

Pure functions only -- no network, no clock reads except the `now` passed in,
no file writes. `tools/ai_news_digest.py` owns fetching and rendering.

A story earns its slot on /news by clearing three independent bars:

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
    MEGA_WIRE_CAP,
    MEGA_WIRE_DOMAINS,
    REQUIRE_KNOWN_SOURCE,
    SOURCE_WEIGHTS,
    TRADE_PRESS_DOMAINS,
    UNKNOWN_CRYPTO_TERMS,
    UNKNOWN_SOURCE_WEIGHT,
)
from ai_news_topic import (
    AI_TERMS,
    HIGH_SIGNAL_PHRASES,
    MARKET_TERMS,
    NOISE_PHRASES,
    count_terms,
    is_on_topic,
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

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")
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


def is_mega_wire(url: str) -> bool:
    return _host_in(url, MEGA_WIRE_DOMAINS)


def recency_factor(
    published: datetime | None,
    now: datetime,
    *,
    half_life_hours: float = RECENCY_HALF_LIFE_HOURS,
    max_age_days: float = MAX_AGE_DAYS,
) -> float:
    """Exponential decay in [0, 1]. Undated stories are treated as one half-life old."""
    if published is None:
        return 0.5
    age_hours = (now - published).total_seconds() / 3600.0
    if age_hours < 0:  # feed clock skew / scheduled posts
        age_hours = 0.0
    if age_hours > max_age_days * 24:
        return 0.0
    return math.pow(0.5, age_hours / half_life_hours)


def score_article(
    article: Article,
    now: datetime,
    *,
    half_life_hours: float = RECENCY_HALF_LIFE_HOURS,
    max_age_days: float = MAX_AGE_DAYS,
) -> float:
    """Score a single story and record why, for auditability."""
    title = article.title.lower()
    summary = article.summary.lower()
    reasons: list[str] = []

    ai_depth = min(
        TITLE_WEIGHT * count_terms(title, AI_TERMS)
        + SUMMARY_WEIGHT * count_terms(summary, AI_TERMS),
        MAX_TERM_HITS * TITLE_WEIGHT,
    )
    market_depth = min(
        TITLE_WEIGHT * count_terms(title, MARKET_TERMS)
        + SUMMARY_WEIGHT * count_terms(summary, MARKET_TERMS),
        MAX_TERM_HITS * TITLE_WEIGHT,
    )
    topic = ai_depth + market_depth

    high_signal = min(
        count_terms(f"{title} {summary}", HIGH_SIGNAL_PHRASES),
        MAX_HIGH_SIGNAL_HITS,
    )
    if high_signal:
        reasons.append(f"{high_signal} AI-executes-trades phrase(s)")

    noise = count_terms(f"{title} {summary}", NOISE_PHRASES)
    if noise:
        reasons.append(f"-{noise} promo phrase(s)")

    raw = topic + HIGH_SIGNAL_BONUS * high_signal - NOISE_PENALTY * noise
    if raw <= 0:
        article.reasons = reasons
        return 0.0

    weight = source_weight(article.publisher_url or article.url)
    decay = recency_factor(
        article.published, now, half_life_hours=half_life_hours, max_age_days=max_age_days,
    )
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
    recency_half_life_hours: float | None = None,
    max_age_days: float | None = None,
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
    half_life = RECENCY_HALF_LIFE_HOURS if recency_half_life_hours is None else recency_half_life_hours
    age_cap = MAX_AGE_DAYS if max_age_days is None else max_age_days

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
            if count_terms(body, UNKNOWN_CRYPTO_TERMS) > 0:
                continue
        article.score = score_article(
            article, now, half_life_hours=half_life, max_age_days=age_cap,
        )
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
        cap = min(MEGA_WIRE_CAP, domain_cap) if is_mega_wire(article.publisher_url or article.url) else domain_cap
        if per_domain.get(domain, 0) >= cap:
            continue
        per_domain[domain] = per_domain.get(domain, 0) + 1
        seen_titles.append(tokens)
        picked.append(article)

    return picked
