"""Compare static publications without treating a clock tick as fresh news."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from ai_news_html import (
    END_MARKER, FEED_END_MARKER, FEED_START_MARKER, START_MARKER,
    feed_payload, inject, render_block, render_feed_block,
)
from ai_news_rank import Article

logger = logging.getLogger(__name__)
STORY_CONTENT_FIELDS = ("source", "domain", "title", "url", "summary", "published")


def publication_unchanged(
    feed: list[Article], teaser: list[Article], *,
    index_path: Path, news_path: Path, json_path: Path,
) -> bool:
    """Keep the prior timestamp only when story content AND rendered blocks match.

    Score and its recency explanation naturally decay without new reporting.
    They remain an honest snapshot at generated_at until the next publication.
    Reading invalid old state is a cache miss; publishers can repair it normally.
    """
    if not all(path.exists() for path in (index_path, news_path, json_path)):
        return False
    try:
        previous = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(previous, dict) or not isinstance(previous.get("stories"), list):
            return False
        old_time = datetime.fromisoformat(previous["generated_at"])
        if old_time.tzinfo is None:
            return False
        current = feed_payload(feed, old_time)
        if any(previous.get(key) != current[key] for key in ("schema_version", "count")):
            return False
        old_stories = previous["stories"]
        if len(old_stories) != len(feed) or any(not isinstance(row, dict) for row in old_stories):
            return False
        for before, after in zip(old_stories, current["stories"]):
            if any(before.get(key) != after[key] for key in STORY_CONTENT_FIELDS):
                return False
        home = index_path.read_text(encoding="utf-8")
        news = news_path.read_text(encoding="utf-8")
        return (
            inject(home, render_block(teaser, old_time), START_MARKER, END_MARKER) == home
            and inject(news, render_feed_block(feed, old_time), FEED_START_MARKER, FEED_END_MARKER) == news
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Unable to compare previous news publication (%s)", type(exc).__name__)
        return False
