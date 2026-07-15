"""Tests for Nova OS P9 archive replay / evening review (fixture JSONL day)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive.capture as capture
import archive.compact as compact
import archive.db as archive_db
import archive.evening_review as evening_review
import archive.replay as replay
from constants import ARCHIVE_SOURCE_IBKR, NOVA_OS_DECISION_BUY, NOVA_OS_DECISION_NO_BUY, NOVA_OS_DECISION_WAIT


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive_db, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(compact, "cache_dir", lambda: tmp_path)
    archive_db.init_db()
    capture.clear_l2_stub_for_tests()
    yield tmp_path


def _seed_replay_day(session_date: str = "2026-07-10") -> None:
    # Pre-market through open-ish bars so setups have something to chew on.
    base = 1_720_000_000.0
    for i in range(30):
        px = 10.0 + i * 0.05
        capture.record_bar(
            symbol="TEST",
            ts=base + i * 60,
            open_=px,
            high=px + 0.1,
            low=px - 0.05,
            close=px + 0.02,
            volume=50_000 + i * 100,
            source=ARCHIVE_SOURCE_IBKR,
            timeframe="1m",
            session_date=session_date,
        )
    capture.record_tape_print(
        symbol="TEST",
        ts=base + 100,
        price=10.5,
        size=200,
        source=ARCHIVE_SOURCE_IBKR,
        session_date=session_date,
    )
    compact.compact_day(session_date)


class TestReplay:
    def test_replay_day_collects_decisions(self, monkeypatch):
        _seed_replay_day()

        # Keep risk/session from hard-halting the whole suite unpredictably:
        # monkeypatch gate_session to always pass so we exercise decide path.
        from nova_os.gates import GateResult

        def _pass_session(risk_state, requested_mode):
            return (
                GateResult("session", True, True, ["SESSION_OK"], {}),
                requested_mode,
                [],
            )

        monkeypatch.setattr("nova_os.decide.gate_session", _pass_session)
        monkeypatch.setattr("nova_os.gates.gate_session", _pass_session)

        result = replay.replay_day("2026-07-10", symbols=["TEST"])
        assert result["ok"] is True
        assert result["record"] is False
        assert result["decision_count"] >= 1
        dec = result["decisions"][0]
        assert dec["symbol"] == "TEST"
        assert dec["decision"] in (NOVA_OS_DECISION_BUY, NOVA_OS_DECISION_WAIT, NOVA_OS_DECISION_NO_BUY)
        assert dec["receipt"]["id"] is None  # record=False

    def test_replay_missing_day(self):
        result = replay.replay_day("1999-01-01")
        assert result["ok"] is False
        assert "missing" in (result.get("error") or "").lower()


class TestEveningReview:
    def test_evening_review_versioned_findings(self, monkeypatch):
        _seed_replay_day()
        from nova_os.gates import GateResult

        def _pass_session(risk_state, requested_mode):
            return (
                GateResult("session", True, True, ["SESSION_OK"], {}),
                requested_mode,
                [],
            )

        monkeypatch.setattr("nova_os.decide.gate_session", _pass_session)

        findings = evening_review.evening_review("2026-07-10", symbols=["TEST"])
        assert findings["version"].startswith("evening-review-")
        assert findings["session_date"] == "2026-07-10"
        assert findings["finding_count"] >= 1
        assert "findings" in findings
