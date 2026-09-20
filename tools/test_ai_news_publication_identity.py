"""Publication identity keeps real edits while suppressing clock-only writes."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

import ai_news_digest as digest
import ai_news_publish as publishing
from test_ai_news_publish import NOW, _unique_feed_articles


@pytest.fixture
def published(tmp_path):
    home, news, dump = (tmp_path / name for name in ("index.html", "news.html", "feed.json"))
    home.write_text(f"{digest.START_MARKER}\nOLD\n{digest.END_MARKER}", encoding="utf-8")
    news.write_text(f"{digest.FEED_START_MARKER}\nOLD\n{digest.FEED_END_MARKER}", encoding="utf-8")
    articles = _unique_feed_articles(80)
    options = dict(index_path=home, news_path=news, feed_json_path=dump)
    assert digest.publish(articles, now=NOW, **options) == 0
    return articles, options, (home, news, dump)


def test_identical_feed_skips_every_write(published, monkeypatch):
    articles, options, paths = published
    before = [path.read_bytes() for path in paths]
    def refuse_write(*args, **kwargs):
        pytest.fail("unchanged publication attempted a filesystem write")
    monkeypatch.setattr(type(paths[0]), "write_text", refuse_write)
    assert digest.publish(articles, now=NOW + timedelta(hours=3), **options) == 0
    assert [path.read_bytes() for path in paths] == before


@pytest.mark.parametrize("field,value", [
    ("summary", "A corrected description of this execution algorithm."),
    ("source", "Corrected outlet name"),
    ("title", "Updated execution algorithm reporting"),
    ("url", "https://www.reuters.com/corrected-story"),
    ("published", NOW - timedelta(minutes=30)),
])
def test_changed_story_content_republishes(published, field, value):
    articles, options, paths = published
    first_url = json.loads(paths[2].read_text())["stories"][0]["url"]
    article = next(row for row in articles if row.url == first_url)
    setattr(article, field, value)
    later = NOW + timedelta(hours=3)
    assert digest.publish(articles, now=later, **options) == 0
    assert json.loads(paths[2].read_text())["generated_at"] == later.isoformat()


@pytest.mark.parametrize("broken", ["[]", "null", "{", '{"stories": 42}',
                                        '{"stories": [], "generated_at": "bad"}'])
def test_invalid_previous_json_is_repaired(published, broken):
    articles, options, paths = published
    paths[2].write_text(broken, encoding="utf-8")
    assert digest.publish(articles, now=NOW, **options) == 0
    assert json.loads(paths[2].read_text())["count"] >= 50


def test_rendering_change_is_not_hidden_by_same_stories(published, monkeypatch):
    articles, options, paths = published
    original = publishing.render_feed_block
    def revised(feed, now):
        return original(feed, now) + "\n<!-- new renderer -->"
    monkeypatch.setattr(publishing, "render_feed_block", revised)
    monkeypatch.setattr(digest, "render_feed_block", revised)
    assert digest.publish(articles, now=NOW + timedelta(hours=3), **options) == 0
    assert "new renderer" in paths[1].read_text()


def test_changed_homepage_selection_is_not_hidden(published):
    articles, options, paths = published
    options["homepage_limit"] = 4
    assert digest.publish(articles, now=NOW + timedelta(hours=3), **options) == 0
    assert paths[0].read_text().count('<li class="news-item">') == 4


def test_wrong_json_row_shape_is_repaired(published):
    articles, options, paths = published
    data = json.loads(paths[2].read_text())
    data["stories"][0] = None
    paths[2].write_text(json.dumps(data), encoding="utf-8")
    assert digest.publish(articles, now=NOW, **options) == 0
    assert isinstance(json.loads(paths[2].read_text())["stories"][0], dict)
