"""News analysis package — catalyst comprehension + explicit impact verdicts.

Builds on the existing Alpaca news / catalyst scan in main.py. Does not place
orders. Rules-first scoring lives in impact.py; source credibility in sources.py.
"""
from news.impact import NewsImpactVerdict, evaluate_news_impact
from news.enrich import build_ticker_news_impact, enrich_catalyst_row, gap_percent_from_snapshot

__all__ = [
    "NewsImpactVerdict",
    "build_ticker_news_impact",
    "enrich_catalyst_row",
    "evaluate_news_impact",
    "gap_percent_from_snapshot",
]
