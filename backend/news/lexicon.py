"""Loughran-McDonald financial lexicon sentiment (pysentiment2).

A hand-built, finance-specific word list (Loughran & McDonald, 2011) widely
used for analyzing 10-Ks and financial news — not a fine-tuned neural model,
just word-list counting. No GPU, no model download, effectively instant.
Runs as a second, independent read of the headline alongside the FinBERT
model in `sentiment.py`. Purely informational: it never changes
`impact_class` or `confidence` — the rules in `impact.py` remain the
authoritative decision layer.

Never raises into the request path: any failure (missing dependency, bad
input) degrades to `{"label": "unavailable", "polarity": None}`.

Classify never loads the word list (#797, as D-015 did for FinBERT): `import
pysentiment2` pulls in nltk and scipy and `ps.LM()` reads its list with pandas,
10.3 s on the desk on 2026-10-07, and the first ticker detail socket after a
start ran it on the HTTP loop. Warmup is a daemon thread at process start
(`warm_lexicon`). Until it finishes, classify returns unavailable and caches
nothing, so a headline scored early is scored again once the list is loaded.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from constants import NEWS_LEXICON_CACHE_MAX_ENTRIES, NEWS_LEXICON_ENABLED

logger = logging.getLogger(__name__)

_UNAVAILABLE: dict[str, Any] = {"label": "unavailable", "polarity": None}

_lexicon: Any = None
_load_attempted = False
_warm_started = False
_warm_lock = threading.Lock()
_loaded = threading.Event()
_cache: dict[str, dict[str, Any]] = {}


def _load_lexicon() -> None:
    """Construct the Loughran-McDonald word-list scorer once per process. Warm thread only."""
    global _lexicon, _load_attempted
    if _load_attempted:
        return
    _load_attempted = True
    try:
        import pysentiment2 as ps

        _lexicon = ps.LM()
    except Exception as exc:  # pragma: no cover - depends on local env
        logger.warning("Loughran-McDonald lexicon unavailable: %s", exc)
        _lexicon = None
    finally:
        _loaded.set()


def warm_lexicon() -> None:
    """Start the background load once when the lexicon is enabled. Never blocks the caller."""
    global _warm_started
    if not NEWS_LEXICON_ENABLED:
        return
    with _warm_lock:
        if _warm_started:
            return
        _warm_started = True
    threading.Thread(target=_load_lexicon, daemon=True, name="lexicon-warm").start()


def wait_loaded(timeout: float | None = None) -> bool:
    """Block until the background load finished (loaded or failed). For tools and tests."""
    return _loaded.wait(timeout)


def classify_headline_lexicon(headline: str | None) -> dict[str, Any]:
    """Return {"label": positive|negative|neutral|unavailable, "polarity": float|None}."""
    text = (headline or "").strip()
    if not text or not NEWS_LEXICON_ENABLED:
        return dict(_UNAVAILABLE)
    if text in _cache:
        return _cache[text]
    if not _loaded.is_set():
        warm_lexicon()  # a caller before the lifespan's warmup (a tool, a test) starts it
        return dict(_UNAVAILABLE)

    lm = _lexicon
    if lm is None:
        result = dict(_UNAVAILABLE)
    else:
        try:
            tokens = lm.tokenize(text)
            score = lm.get_score(tokens)
            positive = int(score.get("Positive", 0))
            negative = int(score.get("Negative", 0))
            if positive > negative:
                label = "positive"
            elif negative > positive:
                label = "negative"
            else:
                label = "neutral"
            result = {"label": label, "polarity": round(float(score.get("Polarity", 0.0)), 4)}
        except Exception as exc:  # pragma: no cover - scoring failure
            logger.warning("Loughran-McDonald scoring failed for headline %r: %s", text[:80], exc)
            result = dict(_UNAVAILABLE)

    if len(_cache) >= NEWS_LEXICON_CACHE_MAX_ENTRIES:
        _cache.pop(next(iter(_cache)))
    _cache[text] = result
    return result
