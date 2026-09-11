"""Nova News criticality bands are rules-first and FinBERT-free."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nova_news.criticality import score_story

NOW = datetime(2026, 9, 11, 14, 0, tzinfo=timezone.utc)


def _article(**kwargs) -> dict:
    base = {
        "headline": "Markets open mixed",
        "summary": "Stocks drifted.",
        "source": "Unknown Weekly",
        "url": "https://example.com/a",
        "created_at": (NOW - timedelta(minutes=20)).isoformat(),
    }
    base.update(kwargs)
    return base


def test_official_filing_plus_critical_language_is_critical():
    scored = score_story(
        _article(
            headline="SEC charges ACME after FDA rejection",
            source="SEC",
            url="https://www.sec.gov/news/acme",
        ),
        now=NOW,
    )
    assert scored.criticality == "critical"
    assert scored.score >= 70
    assert scored.tier == "official"


def test_major_fresh_without_keywords_is_watch_not_critical():
    scored = score_story(
        _article(headline="Dow futures little changed", source="Reuters"),
        now=NOW,
    )
    assert scored.criticality == "watch"
    assert scored.tier == "major"


def test_small_publisher_critical_scoop_is_at_least_high():
    scored = score_story(
        _article(
            headline="Tiny Biotech faces clinical hold",
            source="Hedgeweek",
        ),
        now=NOW,
    )
    assert scored.criticality in ("high", "critical")
    assert scored.tier == "secondary"


def test_stale_story_drops_a_band():
    fresh = score_story(
        _article(headline="Company announces public offering", source="Reuters"),
        now=NOW,
    )
    stale = score_story(
        _article(
            headline="Company announces public offering",
            source="Reuters",
            created_at=(NOW - timedelta(hours=30)).isoformat(),
        ),
        now=NOW,
    )
    assert stale.score < fresh.score
    assert stale.criticality in ("watch", "background", "high")
