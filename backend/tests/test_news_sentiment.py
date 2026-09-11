"""Sentiment classifier must never raise, and must not cold-load FinBERT on scan."""
from __future__ import annotations

import threading

import pytest

from news import sentiment


@pytest.fixture(autouse=True)
def _reset():
    sentiment.reset_for_testing()
    yield
    sentiment.reset_for_testing()


def test_empty_headline_is_unavailable():
    assert sentiment.classify_headline_sentiment(None) == {"label": "unavailable", "score": None}
    assert sentiment.classify_headline_sentiment("") == {"label": "unavailable", "score": None}
    assert sentiment.classify_headline_sentiment("   ") == {"label": "unavailable", "score": None}


def test_classify_does_not_load_pipeline(monkeypatch):
    def _boom():
        raise AssertionError("must not load FinBERT on classify (scan pool)")

    monkeypatch.setattr(sentiment, "_get_pipeline", _boom)
    result = sentiment.classify_headline_sentiment("Company reports record quarterly earnings beat")
    assert result == {"label": "unavailable", "score": None}


def test_classify_uses_already_warm_pipeline():
    sentiment._pipeline = lambda text: [{"label": "positive", "score": 0.91}]
    result = sentiment.classify_headline_sentiment("Company reports record quarterly earnings beat")
    assert result == {"label": "positive", "score": 0.91}


def test_same_headline_is_cached_identically():
    sentiment._pipeline = lambda text: [{"label": "neutral", "score": 0.5}]
    headline = "FDA approves new drug application"
    first = sentiment.classify_headline_sentiment(headline)
    second = sentiment.classify_headline_sentiment(headline)
    assert first == second


def test_warm_pipeline_loads_off_the_caller(monkeypatch):
    started = threading.Event()

    def _load():
        started.set()
        return "model"

    monkeypatch.setattr(sentiment, "_get_pipeline", _load)
    sentiment.warm_pipeline()
    assert started.wait(2.0)
