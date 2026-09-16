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
    assert loaded["prompt_tokens"] == 0
    assert loaded["completion_tokens"] == 0
    assert loaded["actual_usd"] is None
    hist = book.list_history("NVDA")
    assert [row["id"] for row in hist] == [run["id"]]
    assert hist[0]["status"] == "failed"


def test_set_usage_persists_partial_spend(advise_db):
    run = book.create_run(
        symbol="SPCX",
        model="m",
        graph_version=1,
        depth=2,
        session_date="2026-09-16",
    )
    book.update_status(run["id"], "failed", fail_reason="OpenRouter HTTP 402", finished=True)
    book.set_usage(run["id"], prompt_tokens=81000, completion_tokens=14000, actual_usd=0.31)
    loaded = book.get_run(run["id"])
    assert loaded["prompt_tokens"] == 81000
    assert loaded["completion_tokens"] == 14000
    assert loaded["actual_usd"] == 0.31
    latest = book.find_latest("SPCX")
    assert latest is not None
    assert latest["id"] == run["id"]
    assert latest["status"] == "failed"
    assert latest["actual_usd"] == 0.31


def test_find_latest_is_newest_any_status(advise_db):
    older = book.create_run(
        symbol="SPCX",
        model="m",
        graph_version=1,
        depth=2,
        session_date="2026-09-16",
    )
    book.update_status(older["id"], "complete", finished=True)
    newer = book.create_run(
        symbol="SPCX",
        model="m",
        graph_version=1,
        depth=2,
        session_date="2026-09-16",
    )
    book.update_status(newer["id"], "failed", fail_reason="budget", finished=True)
    latest = book.find_latest("SPCX")
    assert latest is not None
    assert latest["id"] == newer["id"]
    assert latest["status"] == "failed"
    hist = book.list_history("SPCX")
    assert [row["status"] for row in hist] == ["failed", "complete"]


def test_v1_book_migrates_usage_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    conn = book.get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE advise_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE advise_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schema_version INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                session_date TEXT NOT NULL,
                created_ts REAL NOT NULL,
                finished_ts REAL,
                model TEXT NOT NULL,
                graph_version INTEGER NOT NULL,
                depth INTEGER NOT NULL,
                status TEXT NOT NULL,
                fail_reason TEXT,
                transcript_json TEXT NOT NULL DEFAULT '[]',
                result_json TEXT,
                cache_key TEXT NOT NULL
            );
            INSERT INTO advise_meta(key, value) VALUES ('schema_version', '1');
            INSERT INTO advise_runs (
                schema_version, symbol, session_date, created_ts, finished_ts,
                model, graph_version, depth, status, fail_reason,
                transcript_json, result_json, cache_key
            ) VALUES (
                1, 'SPCX', '2026-09-16', 1000, 1100, 'sonnet', 1, 2, 'failed',
                'OpenRouter HTTP 402', '[]', NULL, 'SPCX|2026-09-16|sonnet|1|2'
            );
            """
        )
        conn.commit()
    finally:
        conn.close()
    book.init_db()
    loaded = book.get_run(1)
    assert loaded is not None
    assert loaded["schema_version"] == ADVISE_SCHEMA_VERSION
    assert loaded["status"] == "failed"
    assert loaded["fail_reason"] == "OpenRouter HTTP 402"
    assert loaded["prompt_tokens"] == 0
    assert loaded["actual_usd"] is None
    meta = book.get_connection()
    try:
        row = meta.execute(
            "SELECT value FROM advise_meta WHERE key = 'schema_version'"
        ).fetchone()
        assert int(row["value"]) == ADVISE_SCHEMA_VERSION
    finally:
        meta.close()


def test_unknown_schema_refuses(advise_db):
    conn = book.get_connection()
    conn.execute("UPDATE advise_meta SET value = '99' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()
    with pytest.raises(book.AdviseBookError, match="unsupported"):
        book.init_db()


def test_cache_key_shape():
    assert cache_key("AAPL", "2026-09-15", "sonnet", 1, 2) == "AAPL|2026-09-15|sonnet|1|2"
