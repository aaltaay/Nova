"""Tests for the archive REST routes (backend/routes/archive.py).

Covers the P9 hardening additions: /replay?as_of= (no-hindsight point-in-time
decisions), /walk/{day} (rewind timeline), /review/{day} (evening review),
and /ask (journal + archive index lookup) — none of these except /replay
(whole-day, hindsight) had HTTP exposure before.
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
from nova_os.gates import GateResult

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

    def _pass_session(risk_state, requested_mode):
        return (GateResult("session", True, True, ["SESSION_OK"], {}), requested_mode, [])

    monkeypatch.setattr("nova_os.decide.gate_session", _pass_session)
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


class TestReplayRoute:
    def test_replay_without_as_of_is_hindsight(self):
        _seed_day()
        res = client.get(f"/api/archive/replay/{_SESSION_DATE}", params={"limit": 5})
        assert res.status_code == 200
        body = res.json()
        assert body["hindsight"] is True
        assert body["decisions"][0]["replay"]["bar_count"] == 20

    def test_replay_with_as_of_slices_bars(self):
        _seed_day()
        as_of = _BASE_TS + 4 * 60
        res = client.get(f"/api/archive/replay/{_SESSION_DATE}", params={"limit": 5, "as_of": as_of})
        assert res.status_code == 200
        body = res.json()
        assert body["hindsight"] is False
        assert body["as_of_ts"] == as_of
        assert body["decisions"][0]["replay"]["bar_count"] == 5

    def test_replay_bad_date_400(self):
        res = client.get("/api/archive/replay/not-a-date")
        assert res.status_code == 400

    def test_replay_missing_day_404(self):
        res = client.get("/api/archive/replay/1999-01-01")
        assert res.status_code == 404


class TestWalkRoute:
    def test_walk_returns_scrubbable_timeline(self):
        _seed_day()
        res = client.get(f"/api/archive/walk/{_SESSION_DATE}", params={"limit": 5, "step_min": 5})
        assert res.status_code == 200
        body = res.json()
        assert body["hindsight"] is False
        assert body["step_count"] >= 2
        ts_seq = [s["as_of_ts"] for s in body["steps"]]
        assert ts_seq == sorted(ts_seq)
        assert len(set(ts_seq)) == len(ts_seq)  # strictly increasing, no dupes

    def test_walk_bad_date_400(self):
        res = client.get("/api/archive/walk/nope")
        assert res.status_code == 400

    def test_walk_missing_day_404(self):
        res = client.get("/api/archive/walk/1999-01-01")
        assert res.status_code == 404


class TestReviewRoute:
    def test_review_returns_versioned_findings(self):
        _seed_day()
        res = client.get(f"/api/archive/review/{_SESSION_DATE}", params={"limit": 5})
        assert res.status_code == 200
        body = res.json()
        assert body["version"].startswith("evening-review-")
        assert body["finding_count"] >= 1

    def test_review_bad_date_400(self):
        res = client.get("/api/archive/review/nope")
        assert res.status_code == 400


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
