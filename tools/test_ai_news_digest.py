"""Tests for the AI-in-trading homepage digest.

The `test_rejects_*` cases are regressions: every one of them is a real story
that reached the top of the ranking during tuning and should never come back.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ai_news_digest as digest  # noqa: E402
import ai_news_rank as rank  # noqa: E402

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def make(title: str, *, url: str = "https://www.reuters.com/a", summary: str = "",
         hours_old: float = 1.0, publisher: str = "") -> rank.Article:
    return rank.Article(
        title=title,
        url=url,
        summary=summary,
        source="Test",
        published=NOW - timedelta(hours=hours_old),
        publisher_url=publisher,
    )


# --- Topic gate -----------------------------------------------------------

def test_accepts_high_signal_phrase_even_without_title_pairing():
    article = make("BGC Group Executes its First Fully AI Brokered Trade")
    assert rank.is_on_topic(article)


def test_accepts_ai_and_market_terms_in_the_headline():
    assert rank.is_on_topic(make("Bank of Korea Warns of Impact of High-Risk AI Trades"))
    assert rank.is_on_topic(make("He's Letting AI Agents Invest His Money"))
    assert rank.is_on_topic(make("How one hedge-fund manager built his firm on AI agents"))


def test_rejects_ai_only_and_markets_only():
    assert not rank.is_on_topic(make("OpenAI releases a faster image model"))
    assert not rank.is_on_topic(make("Hedge fund manager steps down after 20 years"))


def test_rejects_ai_stock_theme_coverage():
    """Regression: ranked #1 when AI and markets could match anywhere in the body."""
    article = make(
        "Here's Where Wall Street Analysts See Nvidia's Share Price Going",
        summary="Analysts covering the artificial intelligence chipmaker expect trading to stay volatile.",
    )
    assert not rank.is_on_topic(article) or rank.score_article(article, NOW) < rank.MIN_SCORE


def test_rejects_venture_fund_false_positive():
    """Regression: 'Google's AI Fund' matched the retired "ai fund" phrase."""
    article = make(
        "Arva AI opens Research Lab to banish human-in-the-loop for financial crime",
        summary="Arva AI, backed by Y Combinator and Google's AI Fund, announced a research division.",
    )
    assert not rank.is_on_topic(article)


def test_rejects_claude_exchanges_false_positive():
    """Regression: the retired "exchange" market term matched chat exchanges."""
    article = make(
        "Chinese AI labs secretly used millions of Claude exchanges to train their models",
        summary="Anthropic says rival labs harvested exchanges from its assistant.",
    )
    assert not rank.is_on_topic(article)


# --- Source credibility ---------------------------------------------------

def test_unknown_crypto_filler_is_dropped_on_the_open_feed():
    coin = make(
        "XRP Price Could Surpass $5; AI trading bot launches",
        url="https://www.smalldesk.example/xrp",
    )
    real = make(
        "Northlake Prairie Zephyr ships execution algorithm",
        url="https://www.smalldesk.example/desk",
    )
    picks = rank.rank_articles(
        [coin, real], NOW, 6, require_known_source=False, min_score=0.1,
    )
    assert [a.url for a in picks] == [real.url]


def test_spam_exchange_blog_never_publishes():
    article = make(
        "MEXC launches AI trading bots for systematic trading",
        url="https://www.mexc.com/news/x",
    )
    assert rank.is_spam_source(article.url)
    assert rank.rank_articles(
        [article], NOW, 6, require_known_source=False, min_score=0.1,
    ) == []


def test_blocked_press_wire_never_publishes_even_when_unknown_allowed():
    article = make(
        "Tickeron launches new AI trading robots for systematic trading",
        url="https://www.globenewswire.com/news-release/x",
    )
    assert rank.is_blocked_source(article.url)
    assert rank.rank_articles(
        [article], NOW, 6, require_known_source=False, min_score=0.1,
    ) == []


def test_unlisted_domain_never_publishes():
    """Regression: a PRLog release promising 189% returns outranked every newsroom."""
    article = make(
        "Tickeron Launches New AI Trading Robots Hitting 189% Annualized Return",
        url="https://www.prlog.org/123",
    )
    assert not rank.is_known_source(article.url)
    assert rank.rank_articles([article], NOW, 6) == []


def test_press_release_subdomain_does_not_inherit_parent_credibility():
    """Regression: markets.businessinsider.com syndicates paid crypto releases."""
    assert rank.is_known_source("https://www.businessinsider.com/x")
    assert not rank.is_known_source("https://markets.businessinsider.com/x")


def test_source_weight_matches_parent_domain():
    assert rank.source_weight("https://www.reuters.com/x") == 1.0
    assert rank.source_weight("https://feeds.arstechnica.com/x") == rank.SOURCE_WEIGHTS["arstechnica.com"]
    assert rank.source_weight("https://example.invalid/x") == rank.UNKNOWN_SOURCE_WEIGHT


# --- Scoring --------------------------------------------------------------

def test_recency_decays_by_half_life():
    fresh = rank.recency_factor(NOW, NOW)
    one_life = rank.recency_factor(NOW - timedelta(hours=rank.RECENCY_HALF_LIFE_HOURS), NOW)
    assert fresh == pytest.approx(1.0)
    assert one_life == pytest.approx(0.5, abs=0.01)
    assert rank.recency_factor(NOW - timedelta(days=rank.MAX_AGE_DAYS + 1), NOW) == 0.0


def test_newer_story_outranks_identical_older_story():
    new = make("AI hedge fund launches quant trading desk", hours_old=1)
    old = make("AI hedge fund launches quant trading desk", hours_old=200)
    assert rank.score_article(new, NOW) > rank.score_article(old, NOW)


def test_capex_news_is_penalised():
    """Regression: 'Google to Invest $15B in AI Infrastructure' took a homepage slot."""
    capex = make("Google to Invest $15 Billion in AI Infrastructure in Finland")
    real = make("Man Group rebuilds its quant trading desk around AI agents")
    assert rank.score_article(capex, NOW) < rank.score_article(real, NOW)


def test_promo_headline_scores_below_the_floor():
    promo = make("Top 10 AI Stocks To Buy Now For Investing Millionaires")
    assert rank.score_article(promo, NOW) < rank.MIN_SCORE


# --- Dedupe and diversity -------------------------------------------------

def test_canonical_url_strips_tracking():
    assert rank.canonical_url("https://WWW.Reuters.com/a/b/?utm_source=x#top") == \
        "https://www.reuters.com/a/b"


def test_same_story_from_two_feeds_appears_once():
    picks = rank.rank_articles([
        make("AI hedge fund launches quant trading desk", url="https://www.reuters.com/a?utm=1"),
        make("AI hedge fund launches quant trading desk", url="https://www.reuters.com/a"),
    ], NOW, 6)
    assert len(picks) == 1


def test_rewritten_headline_is_treated_as_duplicate():
    picks = rank.rank_articles([
        make("Man Group rebuilds quant trading desk around AI agents", url="https://www.reuters.com/a"),
        make("Man Group rebuilds quant trading desk around AI agents now", url="https://www.cnbc.com/b"),
    ], NOW, 6)
    assert len(picks) == 1


def test_one_outlet_cannot_take_every_slot():
    headlines = (
        "Man Group rebuilds its quant trading desk around AI agents",
        "Citadel deploys a new execution algorithm for equities",
        "Regulators probe algorithmic trading at major banks",
        "Jane Street expands machine-driven market making in Asia",
        "Two Sigma hires for an AI-first systematic trading unit",
    )
    articles = [
        make(title, url=f"https://www.reuters.com/{n}")
        for n, title in enumerate(headlines)
    ]
    picks = rank.rank_articles(articles, NOW, 6)
    assert len(picks) == rank.MAX_PER_DOMAIN


def test_weak_stories_leave_slots_empty_rather_than_filling_them():
    stale = make("AI hedge fund launches quant trading desk", hours_old=24 * 12)
    assert rank.score_article(stale, NOW) < rank.MIN_SCORE
    assert rank.rank_articles([stale], NOW, 6) == []


# --- Feed parsing ---------------------------------------------------------

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>AI hedge fund builds a quant trading desk - Reuters</title>
    <link>https://news.google.com/rss/articles/abc</link>
    <description>&lt;p&gt;A &lt;b&gt;quant&lt;/b&gt; story.&lt;/p&gt;</description>
    <pubDate>Wed, 10 Sep 2026 17:09:44 GMT</pubDate>
    <source url="https://www.reuters.com">Reuters</source>
  </item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Deep learning for market making</title>
    <link rel="alternate" href="https://arxiv.org/abs/1234"/>
    <summary>An execution algorithm study.</summary>
    <updated>2026-09-10T08:00:00Z</updated>
  </entry>
</feed>"""


def test_parses_rss_and_recovers_the_real_publisher():
    article = digest.parse_feed(RSS, "Google News")[0]
    assert article.source == "Reuters"
    assert article.publisher_url == "https://www.reuters.com"
    assert article.domain == "reuters.com"
    assert article.summary == "A quant story."
    assert article.published == datetime(2026, 9, 10, 17, 9, 44, tzinfo=timezone.utc)


def test_strips_the_google_news_publisher_suffix_from_headlines():
    assert digest.parse_feed(RSS, "Google News")[0].title == \
        "AI hedge fund builds a quant trading desk"


def test_parses_atom_entries():
    article = digest.parse_feed(ATOM, "arXiv")[0]
    assert article.title == "Deep learning for market making"
    assert article.url == "https://arxiv.org/abs/1234"
    assert article.published is not None


def test_malformed_feed_yields_no_items_instead_of_raising():
    assert digest.parse_feed(b"<rss><channel><item>", "Broken") == []


def test_parse_date_handles_rfc822_and_iso():
    assert digest.parse_date("Wed, 10 Sep 2026 17:09:44 GMT").hour == 17
    assert digest.parse_date("2026-09-10T08:00:00Z").hour == 8
    assert digest.parse_date("") is None
    assert digest.parse_date("not a date") is None


def test_google_news_echo_summary_is_dropped():
    """Google News descriptions repeat the headline plus the outlet name."""
    echo = b"""<?xml version="1.0"?><rss version="2.0"><channel><item>
      <title>Bank of Korea Warns of AI Trades - WSJ</title>
      <link>https://news.google.com/x</link>
      <description>Bank of Korea Warns of AI Trades&amp;nbsp;&amp;nbsp;WSJ</description>
      <source url="https://www.wsj.com">WSJ</source>
    </item></channel></rss>"""
    assert digest.parse_feed(echo, "Google News")[0].summary == ""


def test_real_summary_is_kept():
    assert digest.parse_feed(RSS, "Google News")[0].summary == "A quant story."


def test_truncate_cuts_on_a_word_boundary():
    assert digest.truncate("alpha beta gamma", 11) == "alpha beta..."
    assert digest.truncate("short", 11) == "short"
