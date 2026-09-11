"""Nova News criticality is rules-first for the AI-in-trading beat."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nova_news.criticality import score_story

NOW = datetime(2026, 9, 11, 14, 0, tzinfo=timezone.utc)


def _article(**kwargs) -> dict:
    base = {
        "headline": "Machine learning comes to the trading desk",
        "summary": "A vendor note.",
        "source": "Unknown Weekly",
        "url": "https://example.com/a",
        "created_at": (NOW - timedelta(minutes=20)).isoformat(),
    }
    base.update(kwargs)
    return base


def test_high_signal_from_a_major_wire_is_critical():
    scored = score_story(
        _article(
            headline="Reuters: Citadel expands its AI trading desk",
            source="Reuters",
        ),
        now=NOW,
    )
    assert scored.criticality == "critical"
    assert scored.score >= 70
    assert scored.tier == "major"
    assert any("doing the trading" in reason for reason in scored.reasons)


def test_headline_pair_without_high_signal_is_not_critical():
    scored = score_story(
        _article(headline="Machine learning comes to the trading desk", source="Reuters"),
        now=NOW,
    )
    assert scored.criticality in ("high", "watch")
    assert scored.score < 70


def test_small_publisher_algo_scoop_is_at_least_high():
    scored = score_story(
        _article(
            headline="Hedgeweek: a quant fund ships a new trading algorithm",
            source="Hedgeweek",
        ),
        now=NOW,
    )
    assert scored.criticality in ("high", "critical")
    assert scored.tier == "secondary"
    assert "executes" in scored.topic_tags


def test_stale_story_drops_points():
    fresh = score_story(
        _article(headline="AI hedge fund opens a New York desk", source="Reuters"),
        now=NOW,
    )
    stale = score_story(
        _article(
            headline="AI hedge fund opens a New York desk",
            source="Reuters",
            created_at=(NOW - timedelta(hours=30)).isoformat(),
        ),
        now=NOW,
    )
    assert stale.score < fresh.score


def test_stock_tip_language_is_penalized():
    clean = score_story(
        _article(headline="AI trading desk adds a new execution algorithm", source="Reuters"),
        now=NOW,
    )
    noisy = score_story(
        _article(
            headline="AI trading desk adds a new execution algorithm -- best AI stocks to buy",
            source="Reuters",
        ),
        now=NOW,
    )
    assert noisy.score < clean.score
