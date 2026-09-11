"""Normalize + ticker extract + dedupe for Nova News."""
from __future__ import annotations

from nova_news.models import ProviderResult
from nova_news.normalize import extract_symbols, stories_from_providers, story_id


def test_extract_symbols_from_cashtag_and_related_not_bare_words():
    article = {
        "headline": "FDA reviews $ABVX after NYSE:CRWV halt chatter",
        "summary": "The US CEO said the IPO is fine.",
        "symbols": "NVDA,MSFT",
    }
    symbols = extract_symbols(article)
    assert "NVDA" in symbols
    assert "MSFT" in symbols
    assert "ABVX" in symbols
    assert "CRWV" in symbols
    assert "US" not in symbols
    assert "CEO" not in symbols
    assert "IPO" not in symbols
    assert "FDA" not in symbols


def test_stories_dedupe_by_url_and_keep_small_publishers():
    results = [
        ProviderResult(
            id="yahoo_news",
            label="Yahoo News",
            ok=True,
            count=2,
            articles=[
                {
                    "headline": "Fed holds rates",
                    "summary": "Wall Street waited.",
                    "url": "https://news.yahoo.com/fed",
                    "source": "Yahoo News",
                    "created_at": "2026-09-11T12:00:00+00:00",
                },
                {
                    "headline": "Local shop covers the tape",
                    "summary": "A regional desk note.",
                    "url": "https://tiny.example/note",
                    "source": "Hedgeweek",
                    "created_at": "2026-09-11T12:05:00+00:00",
                },
            ],
        ),
        ProviderResult(
            id="finnhub",
            label="Finnhub",
            ok=True,
            count=1,
            articles=[
                {
                    "headline": "Fed holds rates",
                    "url": "https://news.yahoo.com/fed",
                    "source": "Reuters",
                    "created_at": "2026-09-11T12:00:00+00:00",
                },
            ],
        ),
    ]
    stories = stories_from_providers(results)
    urls = [s.url for s in stories]
    assert urls.count("https://news.yahoo.com/fed") == 1
    assert any(s.source == "Hedgeweek" for s in stories)
    yahoo = next(s for s in stories if "yahoo" in s.url)
    assert "yahoo" in yahoo.tags
    assert story_id("https://news.yahoo.com/fed", "Fed holds rates") == yahoo.id
