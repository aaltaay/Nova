"""Static HTML / JSON for the marketing-site AI-in-trading digest.

Pure string work -- no network. `ai_news_digest.py` owns fetch + publish.
"""
from __future__ import annotations

import html
import json
from datetime import datetime

from ai_news_rank import Article

START_MARKER = "<!-- AI_NEWS:START -->"
END_MARKER = "<!-- AI_NEWS:END -->"
FEED_START_MARKER = "<!-- AI_NEWS_FEED:START -->"
FEED_END_MARKER = "<!-- AI_NEWS_FEED:END -->"
FEED_JSON_SCHEMA_VERSION = 1


def relative_stamp(published: datetime | None, now: datetime) -> str:
    """Short Reddit-style recency, never an empty string."""
    if published is None:
        return "Recent"
    seconds = (now - published).total_seconds()
    if seconds < 90:
        return "Just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    days = (now.date() - published.date()).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    return f"{days} days ago"


def _item_html(article: Article, index: int, now: datetime, heading: str) -> str:
    stamp = article.published.isoformat() if article.published else now.isoformat()
    summary = (
        f'\n            <p class="news-sum">{html.escape(article.summary)}</p>'
        if article.summary else ""
    )
    return f"""        <li class="news-item">
          <a class="news-link" href="{html.escape(article.url, quote=True)}" rel="noopener noreferrer" target="_blank">
            <p class="news-meta">
              <span class="news-rank">{index:02d}</span>
              <span class="news-src">{html.escape(article.source)}</span>
              <time datetime="{html.escape(stamp, quote=True)}">{relative_stamp(article.published, now)}</time>
            </p>
            <{heading}>{html.escape(article.title)}</{heading}>{summary}
          </a>
        </li>"""


def render_block(articles: list[Article], now: datetime) -> str:
    """Homepage teaser (shortlist)."""
    rows = ['      <ol class="news-list">']
    rows.extend(_item_html(article, i, now, "h3") for i, article in enumerate(articles, start=1))
    rows.append("      </ol>")
    rows.append(
        f'      <p class="news-foot">Homepage shortlist -- not the full desk. '
        f'<a href="/news">Full feed →</a> Ranked by source, topical depth, and recency. '
        f'Updated <time datetime="{now.isoformat()}">{now.strftime("%b %d, %Y %H:%M UTC")}</time>.</p>'
    )
    return "\n".join(rows)


def _feed_item_html(article: Article, index: int, now: datetime) -> str:
    stamp = article.published.isoformat() if article.published else now.isoformat()
    summary = (
        f'\n            <p class="news-sum">{html.escape(article.summary)}</p>'
        if article.summary else ""
    )
    return f"""        <li class="news-item">
          <a class="news-link" href="{html.escape(article.url, quote=True)}" rel="noopener noreferrer" target="_blank">
            <span class="news-rank">{index:02d}</span>
            <p class="news-meta">
              <span class="news-src">{html.escape(article.source)}</span>
              <time datetime="{html.escape(stamp, quote=True)}">{relative_stamp(article.published, now)}</time>
            </p>
            <h3>{html.escape(article.title)}</h3>{summary}
          </a>
        </li>"""


def render_feed_block(articles: list[Article], now: datetime) -> str:
    """Dense Reddit-style list for /news."""
    rows = ['      <ol class="news-feed">']
    rows.extend(_feed_item_html(article, i, now) for i, article in enumerate(articles, start=1))
    rows.append("      </ol>")
    rows.append(
        f'      <p class="news-foot">{len(articles)} AI-in-trading stories. '
        f'Trade press is ranked above mega-wire filler. Headlines link to the publisher. '
        f'Updated <time datetime="{now.isoformat()}">{now.strftime("%b %d, %Y %H:%M UTC")}</time>.</p>'
    )
    return "\n".join(rows)


def inject(page_html: str, block: str, start: str = START_MARKER, end: str = END_MARKER) -> str:
    """Replace whatever sits between the sentinels. Raises if they are missing."""
    start_at = page_html.find(start)
    end_at = page_html.find(end)
    if start_at == -1 or end_at == -1 or end_at < start_at:
        raise ValueError(f"{start} / {end} not found in the page")
    head = page_html[: start_at + len(start)]
    tail = page_html[end_at:]
    return f"{head}\n{block}\n      {tail}"


def count_marked_items(page_html: str, start: str, end: str) -> int:
    start_at = page_html.find(start)
    end_at = page_html.find(end)
    if start_at == -1 or end_at == -1 or end_at < start_at:
        return 0
    return page_html[start_at:end_at].count('<li class="news-item">')


def feed_payload(articles: list[Article], now: datetime) -> dict:
    return {
        "schema_version": FEED_JSON_SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "count": len(articles),
        "stories": [
            {
                "rank": i,
                "score": round(article.score, 2),
                "source": article.source,
                "domain": article.domain,
                "title": article.title,
                "url": article.url,
                "summary": article.summary,
                "published": article.published.isoformat() if article.published else None,
                "why": article.reasons,
            }
            for i, article in enumerate(articles, start=1)
        ],
    }


def feed_json_text(articles: list[Article], now: datetime) -> str:
    return json.dumps(feed_payload(articles, now), indent=2) + "\n"
