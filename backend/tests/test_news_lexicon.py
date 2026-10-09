"""Loughran-McDonald lexicon classifier: never raises, and never loads on the caller's thread (#797)."""
import sys
import threading
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import news.lexicon as lexicon
from news.lexicon import classify_headline_lexicon

UNAVAILABLE = {"label": "unavailable", "polarity": None}


class _FakeLM:
    """Stands in for pysentiment2.LM: records who built it, can be held mid-load."""

    built_on: list[str] = []
    release = threading.Event()

    def __init__(self):
        _FakeLM.built_on.append(threading.current_thread().name)
        assert _FakeLM.release.wait(5), "test never released the load"

    def tokenize(self, text):
        return text.lower().split()

    def get_score(self, tokens):
        pos = sum(t in ("record", "surge", "strong") for t in tokens)
        neg = sum(t in ("plunge", "dilution", "disappointing") for t in tokens)
        return {"Positive": pos, "Negative": neg, "Polarity": (pos - neg) / max(pos + neg, 1)}


def _reset():
    lexicon._lexicon = None
    lexicon._load_attempted = False
    lexicon._warm_started = False
    lexicon._loaded = threading.Event()
    lexicon._cache.clear()


@pytest.fixture
def fake_lm(monkeypatch):
    """A fresh module state with a fake pysentiment2 whose load waits for `release`."""
    _reset()
    _FakeLM.built_on = []
    _FakeLM.release = threading.Event()
    monkeypatch.setitem(sys.modules, "pysentiment2", types.SimpleNamespace(LM=_FakeLM))
    yield _FakeLM
    _FakeLM.release.set()
    lexicon.wait_loaded(5)
    _reset()


def test_empty_headline_is_unavailable():
    assert classify_headline_lexicon(None) == UNAVAILABLE
    assert classify_headline_lexicon("") == UNAVAILABLE
    assert classify_headline_lexicon("   ") == UNAVAILABLE


def test_classify_never_loads_or_waits_on_the_callers_thread(fake_lm):
    # The load is held: a classify that loaded or waited would hang here.
    result = classify_headline_lexicon("Company reports record profit, shares surge")
    assert result == UNAVAILABLE
    assert lexicon.wait_loaded(0) is False
    fake_lm.release.set()
    assert lexicon.wait_loaded(5)
    assert fake_lm.built_on == ["lexicon-warm"]


def test_a_headline_scored_while_loading_is_scored_again_once_loaded(fake_lm):
    headline = "Company reports record profit and strong growth, shares surge"
    assert classify_headline_lexicon(headline) == UNAVAILABLE
    fake_lm.release.set()
    assert lexicon.wait_loaded(5)
    assert classify_headline_lexicon(headline)["label"] == "positive"
    assert classify_headline_lexicon("Disappointing earnings, shares plunge on dilution")["label"] == "negative"


def test_warmup_builds_the_word_list_once(fake_lm):
    threads = [threading.Thread(target=lexicon.warm_lexicon) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    classify_headline_lexicon("FDA approves new drug application")
    fake_lm.release.set()
    assert lexicon.wait_loaded(5)
    assert fake_lm.built_on == ["lexicon-warm"]


def test_a_failed_load_reads_unavailable(monkeypatch):
    _reset()
    monkeypatch.setitem(sys.modules, "pysentiment2", None)  # import raises ImportError
    try:
        lexicon.warm_lexicon()
        assert lexicon.wait_loaded(5)
        assert classify_headline_lexicon("FDA approves new drug application") == UNAVAILABLE
    finally:
        _reset()


def test_disabled_starts_no_load(monkeypatch, fake_lm):
    monkeypatch.setattr(lexicon, "NEWS_LEXICON_ENABLED", False)
    assert classify_headline_lexicon("Shares surge") == UNAVAILABLE
    lexicon.warm_lexicon()
    assert fake_lm.built_on == []
    assert lexicon._warm_started is False


def test_same_headline_is_cached_identically(fake_lm):
    fake_lm.release.set()
    lexicon.warm_lexicon()
    assert lexicon.wait_loaded(5)
    headline = "FDA approves new drug application"
    assert classify_headline_lexicon(headline) == classify_headline_lexicon(headline)
