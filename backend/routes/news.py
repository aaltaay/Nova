"""
News impact routes — READ-ONLY decision layer over existing Alpaca news /
catalyst data. Never places orders.

Endpoints:
  GET /api/news/impact/{symbol}  -- explicit NewsImpactVerdict for one symbol
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from news.impact import evaluate_news_impact
from runtime_state import get_runtime_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/news", tags=["news"])

_TRANSPARENCY_NOTE = (
    "Rules-first news impact verdict. Every threshold is in constants.py "
    "(NEWS_IMPACT_*) and echoed in factors. `sentiment` is a local FinBERT read "
    "of the headline; `lexicon_sentiment` is an independent Loughran-McDonald "
    "financial word-list read; `ai_reasoning` is an opt-in Lincoln AI narrative "
    "(null unless LINCOLN_AI_ENABLED=true + OPENAI_API_KEY are set). None of "
    "the three override impact_class/confidence — the rules remain authoritative."
)


def _gather_context(symbol: str) -> dict:
    """Pull articles + market context from scanner state / ticker helpers."""
    from alpaca import _alpaca_headers
    from ticker import _fetch_ticker_news

    symbol = symbol.upper()
    headers = _alpaca_headers()
    articles: list[dict] = []
    if headers:
        articles = _fetch_ticker_news(symbol, headers)

    gap_percent = None
    rel_volume = None
    state = get_runtime_state()
    for rows in (
        state.news_catalyst_cache,
        state.gapper_cache,
        state.gainer_cache,
        state.afterhours_cache,
    ):
        for row in rows:
            if row.get("symbol") == symbol:
                if gap_percent is None and row.get("gap_percent") is not None:
                    gap_percent = row.get("gap_percent")
                if rel_volume is None:
                    rel_volume = row.get("relative_volume") or row.get("rel_volume")
                if not articles and row.get("catalyst_headline"):
                    articles = [{
                        "headline": row.get("catalyst_headline"),
                        "url": row.get("catalyst_url") or "",
                        "source": row.get("catalyst_source") or "",
                        "created_at": row.get("newest_headline_at") or "",
                    }]
                break

    # Live L2 book when IBKR depth is already subscribed for this symbol.
    l2_features = None
    try:
        from ibkr.depth import current_book
        from l2.features import compute_feature_dict

        book = current_book(symbol)
        if book:
            l2_features = compute_feature_dict(book)
    except Exception:
        logger.debug("routes.news: L2 feature lookup failed for %s, omitting", symbol, exc_info=True)
        l2_features = None

    return {
        "articles": articles,
        "gap_percent": gap_percent,
        "rel_volume": rel_volume,
        "l2_features": l2_features,
    }


@router.get("/impact/{symbol}")
def news_impact(symbol: str) -> dict:
    ctx = _gather_context(symbol)
    verdict = evaluate_news_impact(
        symbol.upper(),
        ctx["articles"],
        gap_percent=ctx["gap_percent"],
        rel_volume=ctx["rel_volume"],
        l2_features=ctx["l2_features"],
    )
    return {
        "note": _TRANSPARENCY_NOTE,
        **verdict.to_dict(),
    }
