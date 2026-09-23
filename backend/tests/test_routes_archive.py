"""Tests for the archive REST routes (backend/routes/archive.py).

Covers /days and /ask (journal + archive index lookup). The decide() replay
routes (/replay, /walk, /review) were retired with the Nova OS verdict
(ADR 025).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.capture as capture
import archive.compact as compact
import archive.db as archive_db
import journal.db as journal_db
from constants import ARCHIVE_SOURCE_IBKR
from main import app

client = TestClient(app)

_SESSION_DATE = "2026-07-10"
_BASE_TS = 1_720_000_000.0


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(compact, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(journal_db, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    journal_db.init_db()
    capture.clear_l2_stub_for_tests()
    yield tmp_path


def _seed_day() -> None:
    for i in range(20):
        px = 10.0 + i * 0.05
        capture.record_bar(
            symbol="TEST",
            ts=_BASE_TS + i * 60,
            open_=px,
            high=px + 0.1,
            low=px - 0.05,
            close=px + 0.02,
            volume=50_000 + i * 100,
            source=ARCHIVE_SOURCE_IBKR,
            timeframe="1m",
            session_date=_SESSION_DATE,
        )
    compact.compact_day(_SESSION_DATE)


class TestDaysRoute:
    def test_days_lists_a_compacted_day(self):
        _seed_day()
        res = client.get("/api/archive/days")
        assert res.status_code == 200
        assert _SESSION_DATE in res.json()["days"]


class TestRetiredDecisionReplay:
    @pytest.mark.parametrize("path", ["replay", "walk", "review"])
    def test_decision_replay_routes_are_gone(self, path):
        """ADR 025 retired the decide() replay with the Nova OS verdict."""
        assert client.get(f"/api/archive/{path}/{_SESSION_DATE}").status_code == 404


class TestAskRoute:
    def test_ask_with_no_filters_returns_shape(self):
        res = client.get("/api/archive/ask")
        assert res.status_code == 200
        body = res.json()
        assert "trades" in body
        assert "archive" in body

    def test_ask_bad_date_400(self):
        res = client.get("/api/archive/ask", params={"session_date": "nope"})
        assert res.status_code == 400
