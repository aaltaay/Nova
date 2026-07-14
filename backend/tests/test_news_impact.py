"""Hard-threshold tests for the rules-first news impact decision layer."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constants import (
    NEWS_IMPACT_AGING_HOURS,
    NEWS_IMPACT_ATTENTION_RVOL,
    NEWS_IMPACT_FRESH_HOURS,
    NEWS_IMPACT_L2_IMBALANCE_MIN,
    NEWS_IMPACT_MILD_MOVE_PCT,
    NEWS_IMPACT_MULTI_SOURCE_CONFIRM,
    NEWS_IMPACT_STALE_HOURS,
    NEWS_IMPACT_STRONG_MOVE_PCT,
)
from news.impact import evaluate_news_impact
from news.enrich import gap_percent_from_snapshot
from news.sources import classify_source_tier, count_confirming_sources


def _now() -> datetime:
    return datetime(2026, 7, 11, 14, 0, 0, tzinfo=timezone.utc)


def _article(*, hours_ago: float, source: str = "Benzinga", url: str = "", headline: str = "Test"):
    created = _now() - timedelta(hours=hours_ago)
    return {
        "headline": headline,
        "source": source,
        "url": url,
        "created_at": created.isoformat().replace("+00:00", "Z"),
    }


class TestSourceTiers:
    def test_official_sec_url(self):
        assert classify_source_tier({"url": "https://www.sec.gov/cgi-bin/browse-edgar", "source": ""}) == "official"

    def test_major_benzinga(self):
        assert classify_source_tier({"source": "Benzinga", "url": ""}) == "major"

    def test_secondary_motley(self):
        assert classify_source_tier({"source": "Motley Fool", "url": ""}) == "secondary"

    def test_unknown_blog(self):
        assert classify_source_tier({"source": "Random Blog XYZ", "url": "https://example.com/x"}) == "unknown"

    def test_multi_source_confirm_count(self):
        arts = [
            _article(hours_ago=0.5, source="Bloomberg"),
            _article(hours_ago=0.6, source="Reuters"),
            _article(hours_ago=0.7, source="Random Blog"),
        ]
        assert count_confirming_sources(arts) >= NEWS_IMPACT_MULTI_SOURCE_CONFIRM


class TestAgeBuckets:
    def test_fresh_bucket_boundary(self):
        v = evaluate_news_impact(
            "AAA",
            [_article(hours_ago=NEWS_IMPACT_FRESH_HOURS)],
            gap_percent=0.0,
            rel_volume=1.0,
            now=_now(),
        )
        assert v.age_bucket == "fresh"

    def test_aging_bucket(self):
        mid = (NEWS_IMPACT_FRESH_HOURS + NEWS_IMPACT_AGING_HOURS) / 2
        v = evaluate_news_impact(
            "AAA",
            [_article(hours_ago=mid)],
            gap_percent=0.0,
            now=_now(),
        )
        assert v.age_bucket == "aging"

    def test_stale_bucket(self):
        mid = (NEWS_IMPACT_AGING_HOURS + NEWS_IMPACT_STALE_HOURS) / 2
        v = evaluate_news_impact(
            "AAA",
            [_article(hours_ago=mid)],
            gap_percent=0.0,
            now=_now(),
        )
        assert v.age_bucket == "stale"

    def test_expired_bucket(self):
        v = evaluate_news_impact(
            "AAA",
            [_article(hours_ago=NEWS_IMPACT_STALE_HOURS + 1)],
            gap_percent=0.20,
            now=_now(),
        )
        assert v.age_bucket == "expired"
        assert v.impact_class == "no_effect"


class TestImpactClassification:
    def test_no_articles_insufficient(self):
        v = evaluate_news_impact("AAA", [], gap_percent=0.15, now=_now())
        assert v.impact_class == "insufficient_data"
        assert v.ai_reasoning is None
        assert any("Lincoln AI" in r for r in v.reasons)

    def test_ai_reasoning_off_by_default(self):
        """LINCOLN_AI_ENABLED defaults False, so no network/API call happens in tests."""
        v = evaluate_news_impact(
            "ZZZ",
            [_article(hours_ago=0.5)],
            gap_percent=0.12,
            now=_now(),
        )
        assert v.ai_reasoning is None
        assert any("Lincoln AI" in r for r in v.reasons)

    def test_sentiment_field_present_and_non_authoritative(self):
        """sentiment/sentiment_score are informational; impact_class is unaffected."""
        v = evaluate_news_impact(
            "YYY",
            [_article(hours_ago=0.5, headline="Test")],
            gap_percent=0.12,
            now=_now(),
        )
        assert v.sentiment in ("positive", "negative", "neutral", "unavailable")
        assert v.impact_class == "moved_price"

    def test_lexicon_field_present_and_non_authoritative(self):
        """lexicon_sentiment/lexicon_polarity are informational; impact_class is unaffected."""
        v = evaluate_news_impact(
            "WWW",
            [_article(hours_ago=0.5, headline="Test")],
            gap_percent=0.12,
            now=_now(),
        )
        assert v.lexicon_sentiment in ("positive", "negative", "neutral", "unavailable")
        assert v.impact_class == "moved_price"

    def test_bump_due_to_news_strong_fresh(self):
        gap = NEWS_IMPACT_STRONG_MOVE_PCT / 100.0
        v = evaluate_news_impact(
            "BBB",
            [_article(hours_ago=0.5, source="Bloomberg")],
            gap_percent=gap,
            rel_volume=1.0,
            now=_now(),
        )
        assert v.impact_class == "moved_price"
        assert v.price_reaction == "strong"
        assert v.confidence >= 0.5
        assert "moved_price" in " ".join(v.reasons)

    def test_mild_move_still_moved_price(self):
        gap = NEWS_IMPACT_MILD_MOVE_PCT / 100.0
        v = evaluate_news_impact(
            "CCC",
            [_article(hours_ago=1.0)],
            gap_percent=gap,
            now=_now(),
        )
        assert v.price_reaction == "mild"
        assert v.impact_class == "moved_price"

    def test_attention_only_elevated_rvol_flat_price(self):
        v = evaluate_news_impact(
            "DDD",
            [_article(hours_ago=1.0)],
            gap_percent=0.01,  # 1% < mild
            rel_volume=NEWS_IMPACT_ATTENTION_RVOL,
            now=_now(),
        )
        assert v.impact_class == "attention_only"
        assert v.attention == "elevated"

    def test_no_effect_flat_normal_rvol(self):
        v = evaluate_news_impact(
            "EEE",
            [_article(hours_ago=1.0)],
            gap_percent=0.005,
            rel_volume=1.0,
            now=_now(),
        )
        assert v.impact_class == "no_effect"

    def test_official_confirmation_flag(self):
        v = evaluate_news_impact(
            "FFF",
            [_article(hours_ago=0.2, source="Business Wire", url="https://www.businesswire.com/x")],
            gap_percent=0.12,
            now=_now(),
        )
        assert v.confirmed_by_official is True
        assert v.source_tier == "official"
        assert v.source_name == "Business Wire"

    def test_source_name_none_when_no_articles(self):
        v = evaluate_news_impact("NNN", [], gap_percent=0.1, now=_now())
        assert v.source_name is None

    def test_headline_url_captured_from_newest_article(self):
        v = evaluate_news_impact(
            "UUU",
            [_article(hours_ago=0.2, source="Reuters", url="https://reuters.com/x", headline="Deal news")],
            gap_percent=0.12,
            now=_now(),
        )
        assert v.headline == "Deal news"
        assert v.headline_url == "https://reuters.com/x"

    def test_l2_reacting_when_imbalance_high(self):
        v = evaluate_news_impact(
            "GGG",
            [_article(hours_ago=0.5)],
            gap_percent=0.12,
            l2_features={"imbalance": NEWS_IMPACT_L2_IMBALANCE_MIN, "bid_heavy": False},
            now=_now(),
        )
        assert v.l2_reaction == "reacting"

    def test_l2_quiet_when_balanced(self):
        v = evaluate_news_impact(
            "HHH",
            [_article(hours_ago=0.5)],
            gap_percent=0.01,
            rel_volume=1.0,
            l2_features={"imbalance": 0.05, "bid_heavy": False},
            now=_now(),
        )
        assert v.l2_reaction == "quiet"

    def test_factors_expose_thresholds(self):
        v = evaluate_news_impact("III", [_article(hours_ago=0.5)], gap_percent=0.1, now=_now())
        assert v.factors["strong_move_pct"] == NEWS_IMPACT_STRONG_MOVE_PCT
        assert v.factors["fresh_hours"] == NEWS_IMPACT_FRESH_HOURS
        assert "observed" in v.factors

    def test_gap_percent_accepts_points_or_fraction(self):
        a = evaluate_news_impact("J1", [_article(hours_ago=0.5)], gap_percent=0.12, now=_now())
        b = evaluate_news_impact("J2", [_article(hours_ago=0.5)], gap_percent=12.0, now=_now())
        assert a.price_reaction == b.price_reaction == "strong"


class TestSnapshotGap:
    def test_gap_from_snapshot_fraction(self):
        snap = {
            "prev_daily_bar": {"close": 10.0},
            "latest_trade": {"price": 12.0},
        }
        assert gap_percent_from_snapshot(snap) == pytest.approx(0.2)
