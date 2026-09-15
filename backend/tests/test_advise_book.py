"""Advise SQLite book: cache key, history, failed partial, schema refuse."""
from __future__ import annotations

import pytest

from advise import book
from advise.events import make_event
from advise.models import cache_key
from constants_advise import ADVISE_GRAPH_VERSION, ADVISE_SCHEMA_VERSION


@pytest.fixture
def advise_db(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    book.init_db()
    return tmp_path


def test_create_and_cache_hit(advise_db):
    run = book.create_run(
        symbol="AAPL",
        model="~anthropic/claude-sonnet-latest",
        graph_version=ADVISE_GRAPH_VERSION,
        depth=2,
        session_date="2026-09-15",
    )
    assert run["status"] == "queued"
    assert run["schema_version"] == ADVISE_SCHEMA_VERSION
    book.append_event(run["id"], make_event("message", agent="bull", content="up"))
    book.set_result(run["id"], {"stance": "LONG", "reasons": ["a"], "risks": ["b"]})
    book.update_status(run["id"], "complete", finished=True)
    hit = book.find_complete_cached(
        symbol="AAPL",
        session_date="2026-09-15",
        model="~anthropic/claude-sonnet-latest",
        graph_version=ADVISE_GRAPH_VERSION,
        depth=2,
    )
    assert hit is not None
    assert hit["id"] == run["id"]
    assert hit["result"]["stance"] == "LONG"
    assert hit["transcript"][0]["agent"] == "bull"
    miss = book.find_complete_cached(
        symbol="AAPL",
        session_date="2026-09-15",
        model="~anthropic/claude-sonnet-latest",
        graph_version=ADVISE_GRAPH_VERSION,
        depth=3,
    )
    assert miss is None


def test_failed_keeps_partial(advise_db):
    run = book.create_run(
        symbol="NVDA",
        model="m",
        graph_version=1,
        depth=2,
        session_date="2026-09-15",
    )
    book.append_event(run["id"], make_event("message", agent="news", content="half"))
    book.update_status(run["id"], "failed", fail_reason="OpenRouter HTTP 401", finished=True)
    loaded = book.get_run(run["id"])
    assert loaded["status"] == "failed"
    assert loaded["fail_reason"] == "OpenRouter HTTP 401"
    assert loaded["transcript"][0]["content"] == "half"
    hist = book.list_history("NVDA")
    assert [row["id"] for row in hist] == [run["id"]]


def test_unknown_schema_refuses(advise_db):
    conn = book.get_connection()
    conn.execute("UPDATE advise_meta SET value = '99' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()
    with pytest.raises(book.AdviseBookError, match="unsupported"):
        book.init_db()


def test_cache_key_shape():
    assert cache_key("AAPL", "2026-09-15", "sonnet", 1, 2) == "AAPL|2026-09-15|sonnet|1|2"
