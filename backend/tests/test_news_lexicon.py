"""Loughran-McDonald lexicon classifier must never raise, regardless of state."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from news.lexicon import classify_headline_lexicon


def test_empty_headline_is_unavailable():
    assert classify_headline_lexicon(None) == {"label": "unavailable", "polarity": None}
    assert classify_headline_lexicon("") == {"label": "unavailable", "polarity": None}
    assert classify_headline_lexicon("   ") == {"label": "unavailable", "polarity": None}


def test_negative_headline_scores_negative():
    result = classify_headline_lexicon("Company reports disappointing earnings, shares plunge on dilution")
    assert result["label"] in ("negative", "unavailable")


def test_positive_headline_scores_positive():
    result = classify_headline_lexicon("Company reports record profit and strong growth, shares surge")
    assert result["label"] in ("positive", "unavailable")


def test_same_headline_is_cached_identically():
    headline = "FDA approves new drug application"
    first = classify_headline_lexicon(headline)
    second = classify_headline_lexicon(headline)
    assert first == second
