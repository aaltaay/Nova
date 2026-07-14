"""Sentiment classifier must never raise, regardless of model/network state."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from news.sentiment import classify_headline_sentiment


def test_empty_headline_is_unavailable():
    assert classify_headline_sentiment(None) == {"label": "unavailable", "score": None}
    assert classify_headline_sentiment("") == {"label": "unavailable", "score": None}
    assert classify_headline_sentiment("   ") == {"label": "unavailable", "score": None}


def test_real_headline_returns_a_known_label():
    result = classify_headline_sentiment("Company reports record quarterly earnings beat")
    assert result["label"] in ("positive", "negative", "neutral", "unavailable")
    if result["label"] != "unavailable":
        assert 0.0 <= result["score"] <= 1.0


def test_same_headline_is_cached_identically():
    headline = "FDA approves new drug application"
    first = classify_headline_sentiment(headline)
    second = classify_headline_sentiment(headline)
    assert first == second
