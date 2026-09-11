"""FinBERT headline sentiment — local, free, no API key required.

Reads the headline text itself (not just its age/source/gap %) and classifies
it positive / negative / neutral using a model already fine-tuned on
financial text. Purely informational: it is surfaced in `NewsImpactVerdict`
alongside the other factors but never changes `impact_class` or `confidence`
— the rules in `impact.py` remain the authoritative decision layer.

Classify never loads the model (D-015): the first scan-pool headline used to
block both SCAN_EXECUTOR_WORKERS on a torch/transformers download. Warmup
is a daemon thread at process start (`warm_pipeline`). Until that finishes,
classify returns unavailable. Any failure degrades the same way — this
module must never raise into the request path.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from constants import (
    NEWS_SENTIMENT_CACHE_MAX_ENTRIES,
    NEWS_SENTIMENT_ENABLED,
    NEWS_SENTIMENT_MODEL_NAME,
)

logger = logging.getLogger(__name__)

_UNAVAILABLE: dict[str, Any] = {"label": "unavailable", "score": None}

_pipeline: Any = None
_load_attempted = False
_warm_started = False
_cache: dict[str, dict[str, Any]] = {}


def _get_pipeline() -> Any:
    """Load the FinBERT pipeline once per process. Call from warmup only."""
    global _pipeline, _load_attempted
    if _pipeline is not None or _load_attempted:
        return _pipeline
    _load_attempted = True
    try:
        from transformers import pipeline as hf_pipeline

        _pipeline = hf_pipeline("sentiment-analysis", model=NEWS_SENTIMENT_MODEL_NAME)
    except Exception as exc:  # pragma: no cover - depends on local env/network
        logger.warning("FinBERT sentiment model unavailable (%s): %s", NEWS_SENTIMENT_MODEL_NAME, exc)
        _pipeline = None
    return _pipeline


def warm_pipeline() -> None:
    """Start a background load when sentiment is enabled. Never blocks the caller."""
    global _warm_started
    if not NEWS_SENTIMENT_ENABLED or _pipeline is not None or _load_attempted or _warm_started:
        return
    _warm_started = True
    threading.Thread(target=_get_pipeline, daemon=True, name="finbert-warm").start()


def classify_headline_sentiment(headline: str | None) -> dict[str, Any]:
    """Return {"label": positive|negative|neutral|unavailable, "score": float|None}.

    Does not trigger a model download. Scan enrich and /api/news/impact stay
    responsive; they see unavailable until `warm_pipeline` finishes.
    """
    text = (headline or "").strip()
    if not text or not NEWS_SENTIMENT_ENABLED:
        return dict(_UNAVAILABLE)
    if text in _cache:
        return _cache[text]

    model = _pipeline
    if model is None:
        result = dict(_UNAVAILABLE)
    else:
        try:
            raw = model(text[:512])[0]
            result = {
                "label": str(raw.get("label", "unavailable")).lower(),
                "score": round(float(raw.get("score", 0.0)), 4),
            }
        except Exception as exc:  # pragma: no cover - inference failure
            logger.warning("FinBERT inference failed for headline %r: %s", text[:80], exc)
            result = dict(_UNAVAILABLE)

    if len(_cache) >= NEWS_SENTIMENT_CACHE_MAX_ENTRIES:
        _cache.pop(next(iter(_cache)))
    _cache[text] = result
    return result


def reset_for_testing() -> None:
    global _pipeline, _load_attempted, _warm_started
    _pipeline = None
    _load_attempted = False
    _warm_started = False
    _cache.clear()
