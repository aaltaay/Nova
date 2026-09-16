"""Junk movers/listicle headlines must not flame or drive news impact."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from news.impact import evaluate_news_impact
from news.junk import (
    filter_signal_articles,
    is_junk_article,
    is_junk_headline,
    newest_signal_by_symbol,
    partition_signal_articles,
)

BENZINGA_MOVERS_HEADLINE = (
    "12 Health Care Stocks Moving In Tuesday's After-Market Session"
)
BENZINGA_MOVERS_URL = (
    "https://www.benzinga.com/trading-ideas/movers/26/09/61805393/"
    "12-health-care-stocks-moving-tuesday-s-after-market-session"
)


def _now() -> datetime:
    return datetime(2026, 9, 16, 14, 0, 0, tzinfo=timezone.utc)


def _article(
    *,
    hours_ago: float,
    headline: str,
    source: str = "Benzinga",
    url: str = "",
    symbols: list[str] | None = None,
) -> dict:
    created = _now() - timedelta(hours=hours_ago)
    return {
        "headline": headline,
        "source": source,
        "url": url,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "symbols": symbols or [],
    }


class TestJunkHeadlines:
    def test_benzinga_movers_example_is_junk(self):
        assert is_junk_headline(BENZINGA_MOVERS_HEADLINE, url=BENZINGA_MOVERS_URL)
        assert is_junk_article(
            {
                "headline": BENZINGA_MOVERS_HEADLINE,
                "url": BENZINGA_MOVERS_URL,
                "source": "Benzinga",
            }
        )

    @pytest.mark.parametrize(
        "headline",
        [
            "5 Tech Stocks Moving In Friday's Pre-Market Session",
            "Stocks Moving In Tuesday's After-Hours Session",
            "Top Premarket Movers For Wednesday",
            "Stocks To Watch: Tesla, Apple, Nvidia",
            "Biggest movers from Tuesday's session",
            "Health Care Stocks To Watch This Week",
            "After-Hours Movers Recap",
            "Today's gainers and losers",
            "Most active stocks in afternoon trade",
        ],
    )
    def test_same_class_listicles_are_junk(self, headline: str):
        assert is_junk_headline(headline) is True

    def test_benzinga_movers_url_is_junk_even_without_headline(self):
        assert is_junk_headline("", url=BENZINGA_MOVERS_URL) is True

    @pytest.mark.parametrize(
        "headline",
        [
            "AAPL surges after-hours on iPhone demand beat",
            "UNH stock moving higher after CMS rate decision",
            "FDA approves PFE COVID booster",
            "JNJ to acquire Abiomed in $16.6 billion merger",
            "Why NVDA is moving after hours",
            "Health care giant UNH reports Q2 earnings miss",
            "12 new patents issued to MDT",
            "SEC files 8-K investigation into after-hours trading at XYZ",
        ],
    )
    def test_company_specific_headlines_are_not_junk(self, headline: str):
        assert is_junk_headline(headline) is False

    def test_sector_roundup_with_named_catalyst_is_kept(self):
        assert (
            is_junk_headline(
                "Health care stocks moving after FDA approves PFE booster"
            )
            is False
        )


class TestIngestHelpers:
    def test_filter_drops_junk_keeps_signal(self):
        junk = _article(
            hours_ago=0.2,
            headline=BENZINGA_MOVERS_HEADLINE,
            url=BENZINGA_MOVERS_URL,
            symbols=["UNH", "PFE"],
        )
        real = _article(
            hours_ago=1.0,
            headline="UNH reports Q2 earnings miss",
            source="Reuters",
            url="https://www.reuters.com/unh-earnings",
            symbols=["UNH"],
        )
        kept = filter_signal_articles([junk, real])
        assert [a["headline"] for a in kept] == [real["headline"]]

    def test_newest_signal_by_symbol_skips_junk_and_prefers_real(self):
        junk = _article(
            hours_ago=0.1,
            headline=BENZINGA_MOVERS_HEADLINE,
            url=BENZINGA_MOVERS_URL,
            symbols=["UNH", "PFE"],
        )
        real = _article(
            hours_ago=2.0,
            headline="UNH reports Q2 earnings miss",
            source="Reuters",
            symbols=["UNH"],
        )
        mapped = newest_signal_by_symbol([junk, real])
        assert mapped["UNH"]["headline"] == "UNH reports Q2 earnings miss"
        assert "PFE" not in mapped

    def test_partition_counts_junk(self):
        junk = _article(hours_ago=0.2, headline="Stocks To Watch Today")
        real = _article(hours_ago=0.3, headline="FDA approves PFE COVID booster")
        kept, dropped = partition_signal_articles([junk, real])
        assert len(kept) == 1
        assert len(dropped) == 1


class TestImpactExclusion:
    def test_junk_only_does_not_moved_price(self):
        v = evaluate_news_impact(
            "UNH",
            [
                _article(
                    hours_ago=0.2,
                    headline=BENZINGA_MOVERS_HEADLINE,
                    url=BENZINGA_MOVERS_URL,
                )
            ],
            gap_percent=0.15,
            now=_now(),
        )
        assert v.impact_class == "insufficient_data"
        assert v.headline is None
        assert any("listicle" in r.lower() or "movers" in r.lower() for r in v.reasons)

    def test_junk_does_not_steal_newest_from_real_news(self):
        junk = _article(
            hours_ago=0.1,
            headline=BENZINGA_MOVERS_HEADLINE,
            url=BENZINGA_MOVERS_URL,
        )
        real = _article(
            hours_ago=0.8,
            headline="UNH reports Q2 earnings miss",
            source="Reuters",
            url="https://www.reuters.com/unh-earnings",
        )
        v = evaluate_news_impact(
            "UNH",
            [junk, real],
            gap_percent=0.12,
            now=_now(),
        )
        assert v.headline == "UNH reports Q2 earnings miss"
        assert v.impact_class == "moved_price"
        assert v.headline_url == "https://www.reuters.com/unh-earnings"

    def test_junk_newest_headline_at_is_ignored_when_only_junk(self):
        junk = _article(
            hours_ago=0.2,
            headline=BENZINGA_MOVERS_HEADLINE,
            url=BENZINGA_MOVERS_URL,
        )
        v = evaluate_news_impact(
            "PFE",
            [junk],
            gap_percent=0.15,
            newest_headline_at=junk["created_at"],
            now=_now(),
        )
        assert v.age_hours is None
        assert v.impact_class == "insufficient_data"


class TestCheckNewsSkipsJunk:
    def test_scanner_check_news_ignores_listicle(self, monkeypatch):
        import scanner

        class FakeResp:
            status_code = 200

            def json(self):
                return {
                    "news": [
                        {
                            "headline": BENZINGA_MOVERS_HEADLINE,
                            "url": BENZINGA_MOVERS_URL,
                            "created_at": "2026-09-16T13:50:00Z",
                            "symbols": ["UNH", "PFE"],
                        },
                        {
                            "headline": "UNH reports Q2 earnings miss",
                            "url": "https://www.reuters.com/unh-earnings",
                            "created_at": "2026-09-16T12:00:00Z",
                            "symbols": ["UNH"],
                        },
                    ]
                }

        monkeypatch.setattr(scanner.requests, "get", lambda *a, **k: FakeResp())
        monkeypatch.setattr(
            scanner,
            "_now_et",
            lambda: datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc),
        )
        out = scanner._check_news(["UNH", "PFE"], {"k": "v"})
        assert out["UNH"] == "2026-09-16T12:00:00Z"
        assert "PFE" not in out


class TestFetchTickerNewsSkipsJunk:
    def test_fetch_ticker_news_drops_listicle(self, monkeypatch):
        import ticker_alpaca

        class FakeResp:
            status_code = 200

            def json(self):
                return {
                    "news": [
                        {
                            "headline": BENZINGA_MOVERS_HEADLINE,
                            "summary": "",
                            "author": "",
                            "source": "Benzinga",
                            "url": BENZINGA_MOVERS_URL,
                            "created_at": "2026-09-16T13:50:00Z",
                            "symbols": ["UNH"],
                            "images": [],
                        },
                        {
                            "headline": "UNH reports Q2 earnings miss",
                            "summary": "Earnings",
                            "author": "",
                            "source": "Reuters",
                            "url": "https://www.reuters.com/unh-earnings",
                            "created_at": "2026-09-16T12:00:00Z",
                            "symbols": ["UNH"],
                            "images": [],
                        },
                    ]
                }

        monkeypatch.setattr(ticker_alpaca.requests, "get", lambda *a, **k: FakeResp())
        monkeypatch.setattr(
            ticker_alpaca,
            "_now_et",
            lambda: datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc),
        )
        news = ticker_alpaca.fetch_ticker_news("UNH", {"k": "v"})
        assert [a["headline"] for a in news] == ["UNH reports Q2 earnings miss"]
