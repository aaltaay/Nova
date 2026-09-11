"""Normalize + ticker extract + AI-trading admission + dedupe."""
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


def test_stories_keep_ai_trading_and_drop_generic_tape():
    results = [
        ProviderResult(
            id="gnews_yahoo",
            label="Yahoo AI trading",
            ok=True,
            count=3,
            articles=[
                {
                    "headline": "Yahoo Finance: Citadel expands its AI trading desk",
                    "summary": "Models now place more of the flow.",
                    "url": "https://finance.yahoo.com/ai-desk",
                    "source": "Yahoo Finance",
                    "created_at": "2026-09-11T12:00:00+00:00",
                },
                {
                    "headline": "Fed holds rates",
                    "summary": "Wall Street waited.",
                    "url": "https://news.yahoo.com/fed",
                    "source": "Yahoo News",
                    "created_at": "2026-09-11T12:00:00+00:00",
                },
                {
                    "headline": "Nvidia share price soars on AI chip demand",
                    "summary": "Analysts lifted targets.",
                    "url": "https://finance.yahoo.com/nvda",
                    "source": "Yahoo Finance",
                    "created_at": "2026-09-11T12:02:00+00:00",
                },
            ],
        ),
        ProviderResult(
            id="hedgeweek",
            label="Hedgeweek",
            ok=True,
            count=1,
            articles=[
                {
                    "headline": "Hedgeweek: a small quant fund ships a trading algorithm",
                    "summary": "Regional desk note.",
                    "url": "https://www.hedgeweek.com/algo",
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
                    "headline": "Yahoo Finance: Citadel expands its AI trading desk",
                    "url": "https://finance.yahoo.com/ai-desk",
                    "source": "Reuters",
                    "created_at": "2026-09-11T12:00:00+00:00",
                },
            ],
        ),
    ]
    stories = stories_from_providers(results)
    urls = [s.url for s in stories]
    assert urls.count("https://finance.yahoo.com/ai-desk") == 1
    assert "https://news.yahoo.com/fed" not in urls
    assert "https://finance.yahoo.com/nvda" not in urls
    assert any(s.source == "Hedgeweek" for s in stories)
    yahoo = next(s for s in stories if "yahoo" in s.url)
    assert "yahoo" in yahoo.tags
    assert "executes" in yahoo.tags
    assert story_id("https://finance.yahoo.com/ai-desk", yahoo.headline) == yahoo.id
