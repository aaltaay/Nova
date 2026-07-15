"""Thin adapters that attach NewsImpactVerdict to scanner / ticker payloads.

Kept separate from impact.py so the pure decision rules stay under the file
size limit and free of IBKR / L2 I/O.
"""
from __future__ import annotations

import logging

from news.impact import evaluate_news_impact

logger = logging.getLogger(__name__)


def enrich_catalyst_row(row: dict) -> dict:
    """Attach a news_impact verdict to a catalyst-scan row (shallow copy)."""
    out = dict(row)
    article = {
        "headline": row.get("catalyst_headline") or "",
        "url": row.get("catalyst_url") or "",
        "source": row.get("catalyst_source") or "",
        "created_at": row.get("newest_headline_at") or "",
    }
    articles = [article] if article["created_at"] or article["headline"] else []
    verdict = evaluate_news_impact(
        str(row.get("symbol") or ""),
        articles,
        gap_percent=row.get("gap_percent"),
        rel_volume=row.get("relative_volume") or row.get("rel_volume"),
        newest_headline_at=row.get("newest_headline_at"),
    )
    out["news_impact"] = verdict.to_dict()
    return out


def gap_percent_from_snapshot(snapshot: dict | None) -> float | None:
    """(last − prev close) / prev close as a fraction, or None if incomplete."""
    if not snapshot:
        return None
    prev_bar = snapshot.get("prev_daily_bar") or snapshot.get("prevDailyBar") or {}
    prev = prev_bar.get("close", prev_bar.get("c"))
    latest = snapshot.get("latest_trade") or snapshot.get("latestTrade") or {}
    last = latest.get("price", latest.get("p"))
    if last is None:
        daily = snapshot.get("daily_bar") or snapshot.get("dailyBar") or {}
        last = daily.get("close", daily.get("c"))
    try:
        if last is None or prev is None or float(prev) == 0:
            return None
        return (float(last) - float(prev)) / float(prev)
    except (TypeError, ValueError):
        return None


def build_ticker_news_impact(
    symbol: str,
    news: list[dict],
    snapshot: dict | None,
    rel_volume: float | None,
) -> dict:
    """Assemble a verdict for ticker detail / WS payloads, including live L2 if present."""
    l2_features = None
    try:
        from ibkr.depth import current_book
        from l2.features import compute_feature_dict

        book = current_book(symbol)
        if book:
            l2_features = compute_feature_dict(book)
    except Exception:
        logger.debug("news.enrich: L2 feature lookup failed for %s, omitting", symbol, exc_info=True)
        l2_features = None
    return evaluate_news_impact(
        symbol,
        news,
        gap_percent=gap_percent_from_snapshot(snapshot),
        rel_volume=rel_volume,
        l2_features=l2_features,
    ).to_dict()
