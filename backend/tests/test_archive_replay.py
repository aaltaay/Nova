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
        # v2 findings carry the exact decision moment they were scored from.
        assert findings["findings"][0]["as_of_ts"] is not None

    def test_outcome_scored_forward_from_decision_not_backward_from_close(self):
        """The v1 bug: outcome looked backward from the day's LAST bar
        regardless of when the decision happened. v2 must score forward from
        as_of_ts, using price *after* the decision, not before it."""
        base = 1_720_000_000.0
        # Flat for 10 minutes, then a sustained rally for the next 20.
        bars = []
        for i in range(30):
            px = 10.0 if i < 10 else 10.0 + (i - 9) * 1.0
            bars.append({"t": "", "o": px, "h": px, "l": px, "c": px, "v": 1000, "ts": base + i * 60})

        decision = {"decision": "BUY", "ticket": {"entry": 10.0}}
        as_of_ts = base + 9 * 60  # right before the rally starts

        outcome = evening_review._outcome_for_decision(
            decision, bars, as_of_ts=as_of_ts, horizon_min=5,
        )
        assert outcome["status"] == "scored"
        assert outcome["decision_ts"] == as_of_ts
        # Forward price must come from AFTER as_of_ts (the rally), not from
        # the flat pre-decision bars and not from the day's final close.
        assert outcome["forward_ts"] > as_of_ts
        assert outcome["forward_price"] > outcome["reference_price"]
        assert outcome["pnl_pct"] > 0
        assert outcome["aligned_with_decision"] is True

    def test_outcome_with_no_forward_bars_is_explicit_not_fabricated(self):
        """A decision at the very last bar has nothing to score forward —
        must say so, not silently reuse stale/backward data."""
        base = 1_720_000_000.0
        bars = [{"t": "", "o": 10.0, "h": 10.0, "l": 10.0, "c": 10.0, "v": 1000, "ts": base}]
        decision = {"decision": "BUY", "ticket": {"entry": 10.0}}
        outcome = evening_review._outcome_for_decision(
            decision, bars, as_of_ts=base, horizon_min=5,
        )
        assert outcome["status"] == "no_forward_bars"
        assert outcome["pnl_pct"] is None


class TestNoHindsight:
    """P9 hardening: decide() must never see bars after the moment it is
    supposedly deciding at."""

    def test_slice_bars_as_of_requires_the_interval_to_have_closed(self):
        """#385: ``ts`` is the bar's OPENING stamp, so a 1m bar opening at 100
        is only known from 160 onward — inclusive at close, never before."""
        bars = [{"ts": 100.0}, {"ts": 200.0}, {"ts": 300.0}]
        assert replay.slice_bars_as_of(bars, 105.0) == []       # +5s into the minute
        assert replay.slice_bars_as_of(bars, 159.0) == []       # one second early
        assert replay.slice_bars_as_of(bars, 160.0) == [{"ts": 100.0}]  # exact close
        assert replay.slice_bars_as_of(bars, 161.0) == [{"ts": 100.0}]
        assert replay.slice_bars_as_of(bars, 260.0) == [{"ts": 100.0}, {"ts": 200.0}]
        assert replay.slice_bars_as_of(bars, 50.0) == []
        assert replay.slice_bars_as_of(bars, 360.0) == bars

    def test_final_minute_ohlcv_is_not_revealed_before_close(self):
        """The issue's own probe, as an executable regression (#385).

        A bar opening at 1789738200 must not hand its high/close/volume to a
        decision made 55 seconds before that minute ends — and must hand them
        over once it has closed. We suppress lookahead, not data.
        """
        bar = {"ts": 1789738200.0, "o": 100.0, "h": 200.0, "l": 99.0, "c": 99.0, "v": 1000}
        early = replay.slice_bars_as_of([bar], 1789738205.0)
        assert early == []
        candidate = replay._candidate_from_bars("TEST", early, "2026-09-20")
        assert candidate["price"] is None
        assert candidate["volume"] == 0

        at_close = replay.slice_bars_as_of([bar], 1789738260.0)
        assert at_close == [bar]
        closed_candidate = replay._candidate_from_bars("TEST", at_close, "2026-09-20")
        assert closed_candidate["price"] == 99.0
        assert closed_candidate["volume"] == 1000

    def test_replay_day_default_is_hindsight_and_says_so(self, monkeypatch):
        _seed_replay_day()
        from nova_os.gates import GateResult

        monkeypatch.setattr(
            "nova_os.decide.gate_session",
            lambda risk_state, requested_mode: (
                GateResult("session", True, True, ["SESSION_OK"], {}), requested_mode, [],
            ),
        )
        result = replay.replay_day("2026-07-10", symbols=["TEST"])
        assert result["hindsight"] is True
        assert result["decisions"][0]["replay"]["bar_count"] == 30  # whole day

    def test_replay_at_slices_bars_and_is_not_hindsight(self, monkeypatch):
        _seed_replay_day()
        from nova_os.gates import GateResult

        monkeypatch.setattr(
            "nova_os.decide.gate_session",
            lambda risk_state, requested_mode: (
                GateResult("session", True, True, ["SESSION_OK"], {}), requested_mode, [],
            ),
        )
        base = 1_720_000_000.0
        # Bar i opens at base + i*60 and closes at base + (i+1)*60. At the
        # 10th bar's OPEN only the first 9 minutes have closed (#385).
        as_of_ts = base + 9 * 60
        result = replay.replay_at("2026-07-10", as_of_ts, symbols=["TEST"])
        assert result["hindsight"] is False
        assert result["as_of_ts"] == as_of_ts
        dec = result["decisions"][0]
        assert dec["replay"]["bar_count"] == 9
        assert dec["replay"]["hindsight"] is False

        # Inclusive at close: one minute later that 10th bar is known.
        at_close = replay.replay_at("2026-07-10", base + 10 * 60, symbols=["TEST"])
        assert at_close["decisions"][0]["replay"]["bar_count"] == 10

    def test_walk_day_never_leaks_future_bars_into_earlier_steps(self, monkeypatch):
        _seed_replay_day()
        from nova_os.gates import GateResult

        monkeypatch.setattr(
            "nova_os.decide.gate_session",
            lambda risk_state, requested_mode: (
                GateResult("session", True, True, ["SESSION_OK"], {}), requested_mode, [],
            ),
        )
        result = replay.walk_day("2026-07-10", symbols=["TEST"], step_min=5)
        assert result["ok"] is True
        assert result["hindsight"] is False
        steps = result["steps"]
        assert len(steps) >= 2

        prev_ts = -1.0
        prev_bar_count = -1
        for step in steps:
            assert step["as_of_ts"] > prev_ts  # strictly increasing walk
            prev_ts = step["as_of_ts"]
            dec = step["decisions"][0]
            bar_count = dec["replay"]["bar_count"]
            assert dec["replay"]["as_of_ts"] == step["as_of_ts"]
            # Cumulative bars seen can only grow (or stay flat) as time moves
            # forward — it must never include bars beyond this step's as_of.
            assert bar_count >= prev_bar_count
            # A bar is known only once its minute has CLOSED (#385).
            expected_max = sum(
                1 for i in range(30) if (1_720_000_000.0 + i * 60 + 60) <= step["as_of_ts"]
            )
            assert bar_count == expected_max
            prev_bar_count = bar_count
        # Final step must still reach the full day — this passes only because
        # _walk_steps now ends at the last bar's CLOSE rather than its open.
        assert steps[-1]["decisions"][0]["replay"]["bar_count"] == 30

    def test_walk_final_step_lands_on_last_bar_close(self, monkeypatch):
        _seed_replay_day()
        from nova_os.gates import GateResult

        monkeypatch.setattr(
            "nova_os.decide.gate_session",
            lambda risk_state, requested_mode: (
                GateResult("session", True, True, ["SESSION_OK"], {}), requested_mode, [],
            ),
        )
        result = replay.walk_day("2026-07-10", symbols=["TEST"], step_min=5)
        last_bar_ts = 1_720_000_000.0 + 29 * 60
        assert result["steps"][-1]["as_of_ts"] == last_bar_ts + 60

    def test_first_walk_step_sees_no_closed_bar(self, monkeypatch):
        """At the very first as-of nothing has closed yet — decide() must
        still produce a decision rather than choking on an empty bar list."""
        _seed_replay_day()
        from nova_os.gates import GateResult

        monkeypatch.setattr(
            "nova_os.decide.gate_session",
            lambda risk_state, requested_mode: (
                GateResult("session", True, True, ["SESSION_OK"], {}), requested_mode, [],
            ),
        )
        result = replay.walk_day("2026-07-10", symbols=["TEST"], step_min=5)
        first = result["steps"][0]
        assert first["as_of_ts"] == 1_720_000_000.0
        assert first["errors"] == []
        assert first["decisions"][0]["replay"]["bar_count"] == 0

    def test_walk_day_missing_day(self):
        result = replay.walk_day("1999-01-01")
        assert result["ok"] is False
        assert "missing" in (result.get("error") or "").lower()
