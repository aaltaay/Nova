"""Tests for the AI-in-trading homepage digest.

The `test_rejects_*` cases are regressions: every one of them is a real story
that reached the top of the ranking during tuning and should never come back.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ai_news_digest as digest  # noqa: E402
import ai_news_rank as rank  # noqa: E402

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def make(title: str, *, url: str = "https://www.reuters.com/a", summary: str = "",
         hours_old: float = 1.0, publisher: str = "") -> rank.Article:
    return rank.Article(
        title=title,
        url=url,
        summary=summary,
        source="Test",
        published=NOW - timedelta(hours=hours_old),
        publisher_url=publisher,
    )


# --- Rendering ------------------------------------------------------------

def test_render_escapes_untrusted_feed_text():
    article = make('Quant <script>alert(1)</script> & AI trading desk')
    block = digest.render_block([article], NOW)
    assert "<script>" not in block
    assert "&lt;script&gt;" in block
    assert "&amp;" in block


def test_inject_replaces_only_the_marked_region():
    page = f"<main>\n      {digest.START_MARKER}\nOLD\n      {digest.END_MARKER}\n</main>"
    out = digest.inject(page, "NEW")
    assert "OLD" not in out
    assert "NEW" in out
    assert out.startswith("<main>")
    assert out.endswith("</main>")


def test_inject_refuses_a_page_without_markers():
    with pytest.raises(ValueError):
        digest.inject("<main></main>", "NEW")


def test_injection_is_idempotent():
    page = f"{digest.START_MARKER}\nOLD\n      {digest.END_MARKER}"
    once = digest.inject(page, "NEW")
    assert digest.inject(once, "NEW") == once


def test_live_page_carries_the_markers():
    page = digest.INDEX_HTML.read_text(encoding="utf-8")
    assert digest.START_MARKER in page
    assert digest.END_MARKER in page


def test_news_page_carries_the_markers():
    page = digest.NEWS_HTML.read_text(encoding="utf-8")
    assert digest.FEED_START_MARKER in page
    assert digest.FEED_END_MARKER in page
    assert 'class="news-feed"' in page


def test_homepage_teaser_points_at_full_feed():
    page = digest.INDEX_HTML.read_text(encoding="utf-8")
    assert 'href="/news"' in page
    assert "Full feed" in page


def _unique_feed_articles(count: int) -> list[rank.Article]:
    domains = [d for d in rank.SOURCE_WEIGHTS if d not in rank.BLOCKED_DOMAINS]
    articles = []
    for i in range(count):
        domain = domains[i % len(domains)]
        articles.append(make(
            f"Northlake{i} Prairie{i} Zephyr{i} ships execution algorithm",
            url=f"https://www.{domain}/story-{i}",
            hours_old=1.0 + (i * 0.05),
        ))
    return articles


def test_rank_articles_can_return_fifty_when_inventory_exists():
    picks = rank.rank_articles(
        _unique_feed_articles(80),
        NOW,
        50,
        max_per_domain=10,
        min_score=1.0,
    )
    assert len(picks) >= 50


def test_homepage_ranking_still_caps_one_outlet():
    articles = _unique_feed_articles(20)
    # Force every URL onto Reuters so the default domain cap still holds.
    for i, article in enumerate(articles):
        article.url = f"https://www.reuters.com/forced-{i}"
        article.publisher_url = "https://www.reuters.com"
    picks = rank.rank_articles(articles, NOW, 50)
    assert len(picks) == rank.MAX_PER_DOMAIN


def test_refuse_thin_feed_keeps_existing_page(tmp_path: Path):
    good = [make(
        f"Northlake{i} Prairie{i} Zephyr{i} ships execution algorithm",
        url=f"https://www.marketsmedia.com/keep-{i}",
        hours_old=1.0,
    ) for i in range(50)]
    home = tmp_path / "index.html"
    news = tmp_path / "news" / "index.html"
    dump = tmp_path / "news" / "feed.json"
    news.parent.mkdir()
    home.write_text(
        f"<main>{digest.START_MARKER}\nOLD HOME\n      {digest.END_MARKER}</main>",
        encoding="utf-8",
    )
    news.write_text(
        digest.inject(
            f"{digest.FEED_START_MARKER}\nOLD FEED\n      {digest.FEED_END_MARKER}",
            digest.render_feed_block(good, NOW),
            digest.FEED_START_MARKER,
            digest.FEED_END_MARKER,
        ),
        encoding="utf-8",
    )
    before = news.read_text(encoding="utf-8")
    thin = _unique_feed_articles(8)
    code = digest.publish(
        thin,
        now=NOW,
        homepage_limit=6,
        feed_limit=60,
        homepage_min=4,
        feed_min=50,
        index_path=home,
        news_path=news,
        feed_json_path=dump,
    )
    assert code == 0
    assert news.read_text(encoding="utf-8") == before
    assert not dump.exists()
    assert "OLD HOME" not in home.read_text(encoding="utf-8")
    assert home.read_text(encoding="utf-8").count('<li class="news-item">') >= 4


def test_thin_homepage_exits_nonzero_without_writes(tmp_path: Path):
    home = tmp_path / "index.html"
    news = tmp_path / "news.html"
    dump = tmp_path / "feed.json"
    home.write_text(
        f"{digest.START_MARKER}\nKEEP\n      {digest.END_MARKER}",
        encoding="utf-8",
    )
    news.write_text(
        f"{digest.FEED_START_MARKER}\nKEEP FEED\n      {digest.FEED_END_MARKER}",
        encoding="utf-8",
    )
    code = digest.publish(
        [],
        now=NOW,
        homepage_min=4,
        feed_min=50,
        index_path=home,
        news_path=news,
        feed_json_path=dump,
    )
    assert code == 1
    assert "KEEP" in home.read_text(encoding="utf-8")
    assert "KEEP FEED" in news.read_text(encoding="utf-8")


def test_publish_writes_feed_json_when_inventory_clears_floor(tmp_path: Path):
    home = tmp_path / "index.html"
    news = tmp_path / "news" / "index.html"
    dump = tmp_path / "news" / "feed.json"
    news.parent.mkdir()
    home.write_text(
        f"{digest.START_MARKER}\nOLD\n      {digest.END_MARKER}",
        encoding="utf-8",
    )
    news.write_text(
        f"{digest.FEED_START_MARKER}\nOLD\n      {digest.FEED_END_MARKER}",
        encoding="utf-8",
    )
    code = digest.publish(
        _unique_feed_articles(80),
        now=NOW,
        homepage_limit=6,
        feed_limit=60,
        homepage_min=4,
        feed_min=50,
        index_path=home,
        news_path=news,
        feed_json_path=dump,
    )
    assert code == 0
    payload = json.loads(dump.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["count"] >= 50
    assert digest.count_marked_items(
        news.read_text(encoding="utf-8"),
        digest.FEED_START_MARKER,
        digest.FEED_END_MARKER,
    ) >= 50


def test_render_feed_escapes_untrusted_feed_text():
    article = make('Quant <script>alert(1)</script> & AI trading desk')
    block = digest.render_feed_block([article], NOW)
    assert "<script>" not in block
    assert "&lt;script&gt;" in block
    assert 'class="news-feed"' in block
