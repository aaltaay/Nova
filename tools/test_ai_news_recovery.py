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
from test_ai_news_digest import RSS  # noqa: E402

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



def test_google_news_youtube_is_spam():
    """Google News wraps YouTube; the publisher host is what we block."""
    article = make(
        "I Built a Claude AI Trading Bot for Live Trading",
        url="https://news.google.com/rss/articles/abc",
        publisher="https://youtu.be/abc",
    )
    assert rank.is_spam_source(article.publisher_url)
    assert rank.rank_articles(
        [article], NOW, 6, require_known_source=False, min_score=0.1,
    ) == []


def test_access_newswire_is_blocked():
    article = make(
        "OmniPhi launches agentic trading for systematic trading",
        url="https://www.accessnewswire.com/newsroom/x",
    )
    assert rank.is_blocked_source(article.url)
    assert rank.rank_articles(
        [article], NOW, 6, require_known_source=False, min_score=0.1,
    ) == []


def test_rejects_ai_stock_boom_banker_tooling_and_review_farms():
    assert not rank.is_on_topic(make(
        "Wall Street firm believes the AI stock market boom is nearing an end",
    ))
    assert not rank.is_on_topic(make(
        "OpenAI targets work of Wall Street junior bankers with ChatGPT for Financial Services",
    ))
    assert not rank.is_on_topic(make(
        "UAE Plans to Invest $46 Billion in Germany From AI to Energy",
    ))
    assert not rank.is_on_topic(make(
        "AI Trading Engine Review My Real Test With Results & Demo.png",
    ))
    assert not rank.is_on_topic(make(
        "Motilal Oswal Quant Fund - Regular Plan Returns",
    ))


def test_ai_agents_invest_headline_still_qualifies():
    assert rank.is_on_topic(make("He's Letting AI Agents Invest His Money"))


def test_trading_cards_are_not_the_beat():
    assert not rank.is_on_topic(make(
        "CardSight AI Expands Trading Card Infrastructure to MMA",
    ))


def test_ai_stock_unwind_is_not_the_beat():
    assert not rank.is_on_topic(make(
        "Hedge funds posted their worst month against the S&P 500 in 20 years as AI bets unwound",
    ))
    assert not rank.is_on_topic(make(
        "Crowded AI trades hit hedge funds as quant and stockpickers cut risk",
    ))
    assert not rank.is_on_topic(make(
        "Epic AI Circle Public Feud: Codex & Claude Code Leaders Openly Trade Insults",
        url="https://eu.36kr.com/x",
    ))
    assert not rank.is_on_topic(make(
        'Canadian Securities Exchange Welcomes Listing of Pelican AI, Trading Under Symbol "PEL"',
    ))


def test_job_board_listings_are_not_news():
    article = make(
        "Machine Learning Researcher - Quantitative Trading- Leading Market-Maker / Hedge Fund",
        url="https://www.efinancialcareers.com/jobs/x",
    )
    assert rank.is_spam_source(article.url)
    assert rank.rank_articles(
        [article], NOW, 6, require_known_source=False, min_score=0.1,
    ) == []


def test_claude_investment_process_is_on_topic():
    assert rank.is_on_topic(make(
        "T. Rowe Price Expands Use of Claude in its Investment Process",
        url="https://www.tradersmagazine.com/t-rowe",
    ))
    assert rank.is_on_topic(make(
        "Goldman Sachs Sees AI Reshaping Institutional Investing",
        url="https://www.tradersmagazine.com/gs",
    ))


def test_mega_wires_cannot_dominate_the_feed():
    articles = [
        make(
            f"Northlake{i} Prairie{i} Zephyr{i} ships execution algorithm",
            url=f"https://www.cnbc.com/story-{i}",
            hours_old=1.0,
        )
        for i in range(8)
    ]
    picks = rank.rank_articles(
        articles, NOW, 50, max_per_domain=10, min_score=0.1, require_known_source=False,
    )
    assert len(picks) == rank.MEGA_WIRE_CAP


def test_decode_gzip_feed_body():
    import gzip

    raw = gzip.compress(RSS)
    assert digest.decode_feed_body(raw).startswith(b"<?xml")
    assert digest.decode_feed_body(RSS) == RSS


@pytest.mark.parametrize("body", [b"\x1f\x8b", b"\x1f\x8bnot-valid-gzip"])
def test_malformed_compressed_feed_is_unavailable(monkeypatch, capsys, body):
    from io import BytesIO

    monkeypatch.setattr(digest.urllib.request, "urlopen", lambda *a, **kw: BytesIO(body))
    assert digest.fetch_feed("Broken gzip", "https://example.com/feed") == []
    assert "unreachable" in capsys.readouterr().err


def test_mega_wire_obeys_stricter_caller_cap():
    rows = [make(f"Northlake{i} Prairie{i} Zephyr{i} execution algorithm",
                 url=f"https://www.reuters.com/story-{i}") for i in range(4)]
    assert len(rank.rank_articles(rows, NOW, 10, max_per_domain=1)) == 1


def test_full_feed_age_cutoff_does_not_change_teaser():
    old = make("Waters desk ships execution algorithm",
               url="https://www.waterstechnology.com/old", hours_old=24 * 40)
    assert digest.rank_teaser([old], NOW, 6) == []
    old.published = NOW - timedelta(days=91)
    assert digest.rank_feed([old], NOW, 60) == []


def test_older_trade_press_still_fills_the_public_feed():
    old = make(
        "Waters desk ships a new execution algorithm",
        url="https://www.waterstechnology.com/old-story",
        hours_old=24 * 40,
    )
    picks = digest.rank_feed([old], NOW, 10)
    assert [a.url for a in picks] == [old.url]


def test_native_trade_press_feeds_are_listed():
    urls = " ".join(url for _label, url in digest.FEEDS)
    assert "thetradenews.com/feed" in urls
    assert "waterstechnology.com/feeds/rss" in urls
    assert "risk.net/feeds/rss" in urls
    assert "institutionalinvestor.com/rss.xml" in urls
    assert "site:tradersmagazine.com" in urls
    assert "site:finextra.com" in urls
