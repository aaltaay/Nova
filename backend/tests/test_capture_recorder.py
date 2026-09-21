"""Regression coverage for backend/capture (D-063, D-067, D-068, D-075).

Every test that touches Stop goes through ``_stop_within`` rather than calling
``stop_recorder()`` directly.  ``recorder._lock`` is a non-reentrant
``threading.Lock`` on purpose, so a re-entrancy regression (D-063) deadlocks
instead of raising -- without a timeout guard that would hang CI forever rather
than failing it.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

import pytest

from capture import bar_buckets, manifest_io, mode, recorder, session_state
from capture.constants_capture import (
    CAPTURE_MAX_WRITE_FAILURES,
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_INTERRUPTED,
    CAPTURE_STATUS_STOPPED,
)

STOP_TIMEOUT_SEC = 10.0


def _call_guarded(fn, timeout: float) -> tuple[bool, BaseException | None]:
    """Run ``fn`` on a daemon thread; report whether it returned in time.

    A deadlocked thread stays parked on the old lock forever, but daemon threads
    do not hold up interpreter exit, so the suite keeps moving.
    """
    done = threading.Event()
    error: list[BaseException] = []

    def _run() -> None:
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised by the caller
            error.append(exc)
        finally:
            done.set()

    threading.Thread(target=_run, name="capture-stop-probe", daemon=True).start()
    return done.wait(timeout), (error[0] if error else None)


def _hard_reset_recorder() -> None:
    """Abandon a wedged lock so one deadlock does not hang every later test."""
    recorder._hard_reset_for_tests()


def _reset_recorder() -> bool:
    """Reset the recorder without ever hanging. False if it had to be forced."""
    returned, error = _call_guarded(recorder.reset_for_tests, STOP_TIMEOUT_SEC)
    if not returned:
        _hard_reset_recorder()
        return False
    if error is not None:
        raise error
    return True


@pytest.fixture(autouse=True)
def _capture_root(tmp_path, monkeypatch):
    """Never touch the operator's F:\\Nova\\sim_capture or backend/.cache."""
    root = tmp_path / "sim_capture"
    root.mkdir()
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(root))
    from capture import bridge_ibkr
    monkeypatch.setattr(bridge_ibkr, "admission_error", lambda symbol: None)
    bar_buckets.reset_for_tests()
    session_state.reset_for_tests()
    mode.reset_for_tests()
    assert _reset_recorder(), "recorder was already wedged before this test started"
    yield root
    wedged = not _reset_recorder()
    bar_buckets.reset_for_tests()
    session_state.reset_for_tests()
    mode.reset_for_tests()
    assert not wedged, (
        "stop_recorder() deadlocked during teardown — the stop path re-entered "
        "the non-reentrant recorder lock (D-063 regression)"
    )


def _stop_within(timeout: float = STOP_TIMEOUT_SEC) -> None:
    """Stop the recorder, failing (not hanging) if the stop path deadlocks."""
    returned, error = _call_guarded(recorder.stop_recorder, timeout)
    if not returned:
        held, active = recorder._lock.locked(), recorder.is_recording()
        _hard_reset_recorder()
        pytest.fail(
            f"stop_recorder() did not return within {timeout}s — the stop path "
            "re-entered the non-reentrant recorder lock (D-063 regression). "
            f"lock held={held} active={active}"
        )
    if error is not None:
        raise error


def _session_dir() -> Path:
    return Path(recorder.status()["dir"])


def _manifest(session_dir: Path | None = None) -> dict:
    target = session_dir or _session_dir()
    return json.loads((target / "manifest.json").read_text(encoding="utf-8"))


def _feed_prints(symbol: str, n: int, *, start_ts: float = 1_700_000_000.0) -> None:
    """Drive the same path the Sim bridge uses: record + roll bar buckets."""
    for i in range(n):
        ts = start_ts + i
        recorder.record_print({"symbol": symbol, "ts": ts, "price": 10.0 + i, "size": 100})
        bar_buckets.on_print(symbol, ts, 10.0 + i, 100.0, source="sim", session_date="2026-09-20")


# --------------------------------------------------------------------------
# D-063 -- the stop path must not re-enter the recorder lock
# --------------------------------------------------------------------------


def test_lock_is_non_reentrant() -> None:
    """An RLock would paper over D-063 and make the timeout guards useless."""
    assert not isinstance(recorder._lock, type(threading.RLock()))


def test_stop_with_open_bar_buckets_returns() -> None:
    """The original D-063 repro: Stop after the first print deadlocked forever."""
    recorder.start_recorder("DEAD")
    _feed_prints("DEAD", 5)
    assert recorder.status()["counts"]["prints"] == 5

    _stop_within()

    assert recorder.is_recording() is False
    assert recorder._lock.locked() is False


def test_stop_flushes_open_buckets_to_disk() -> None:
    """Draining the buckets must still *write* them, not just avoid the lock."""
    recorder.start_recorder("FLUSH")
    _feed_prints("FLUSH", 3)
    session_dir = _session_dir()
    open_10s = (session_dir / "bars_10s.jsonl").read_text(encoding="utf-8").count("\n")

    _stop_within()

    flushed = (session_dir / "bars_10s.jsonl").read_text(encoding="utf-8").count("\n")
    assert flushed > open_10s, "the open 10s bucket was dropped instead of flushed"
    assert _manifest(session_dir)["counts"]["bars_10s"] == flushed


def test_restart_on_second_symbol_returns() -> None:
    """A second symbol starts inside the same lock the first holds (D-063), beside it."""
    recorder.start_recorder("ONE")
    _feed_prints("ONE", 3)

    returned, error = _call_guarded(lambda: recorder.start_recorder("TWO"), STOP_TIMEOUT_SEC)
    if not returned:
        _hard_reset_recorder()
        pytest.fail("starting a second recording deadlocked (D-063 regression)")
    if error is not None:
        raise error
    assert sorted(recorder.recording_symbols()) == ["ONE", "TWO"]
    assert recorder.status("TWO")["recording"] and recorder.status("ONE")["counts"]["prints"] == 3
    _stop_within()
    assert recorder.recording_symbols() == []


def test_recording_survives_concurrent_writers_during_stop() -> None:
    """A tape thread writing while Stop runs must not wedge either side."""
    recorder.start_recorder("RACE")
    stop_now = threading.Event()
    writer_done = threading.Event()

    def _writer() -> None:
        while not stop_now.is_set():
            recorder.record_print({"symbol": "RACE", "ts": 1.0, "price": 1.0, "size": 1})
        writer_done.set()

    threading.Thread(target=_writer, daemon=True).start()
    _feed_prints("RACE", 2)
    _stop_within()
    stop_now.set()
    assert writer_done.wait(STOP_TIMEOUT_SEC), "a tape writer stayed blocked on the lock"
    assert recorder.is_recording() is False


# --------------------------------------------------------------------------
# D-067 -- crash safety: shutdown finalization, atomic + merged manifest
# --------------------------------------------------------------------------


def test_stop_writes_terminal_counts_and_status() -> None:
    recorder.start_recorder("TERM")
    _feed_prints("TERM", 4)
    session_dir = _session_dir()

    _stop_within()

    man = _manifest(session_dir)
    assert man["status"] == CAPTURE_STATUS_STOPPED
    assert man["stopped_et"]
    assert man["counts"]["prints"] == 4
    assert len(man["segments"]) == 1


def test_resume_merges_instead_of_destroying_prior_counts() -> None:
    """D-067b: counts restarted at zero while the jsonl kept appending."""
    recorder.start_recorder("MERGE")
    _feed_prints("MERGE", 5)
    session_dir = _session_dir()
    _stop_within()
    first_started = _manifest(session_dir)["started_et"]

    recorder.start_recorder("MERGE")
    _feed_prints("MERGE", 3, start_ts=1_700_100_000.0)
    _stop_within()

    man = _manifest(session_dir)
    rows_on_disk = sum(
        1 for line in (session_dir / "prints.jsonl").read_text(encoding="utf-8").splitlines() if line
    )
    assert man["counts"]["prints"] == rows_on_disk == 8, "manifest understates the file"
    assert man["started_et"] == first_started, "resume destroyed the original start time"
    assert len(man["segments"]) == 2
    assert [s["counts"]["prints"] for s in man["segments"]] == [5, 3]


def test_resume_false_truncates_and_starts_a_fresh_manifest() -> None:
    """The dead ``resume`` parameter is now honoured rather than ignored."""
    recorder.start_recorder("FRESH")
    _feed_prints("FRESH", 5)
    session_dir = _session_dir()
    _stop_within()

    recorder.start_recorder("FRESH", resume=False)
    _feed_prints("FRESH", 2, start_ts=1_700_200_000.0)
    _stop_within()

    man = _manifest(session_dir)
    rows_on_disk = sum(
        1 for line in (session_dir / "prints.jsonl").read_text(encoding="utf-8").splitlines() if line
    )
    assert man["counts"]["prints"] == rows_on_disk == 2
    assert man["resume"] is False


def test_manifest_write_is_atomic(_capture_root) -> None:
    """Temp + os.replace: a reader never sees a half-written manifest."""
    target = _capture_root / "manifest.json"
    target.write_text('{"old": true}', encoding="utf-8")
    manifest_io.write_json_atomic(target, {"new": True, "counts": {"prints": 1}})

    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True, "counts": {"prints": 1}}
    assert not list(_capture_root.glob("manifest.json.tmp*")), "temp file was left behind"


def test_interrupted_session_is_finalized_on_restart(_capture_root) -> None:
    """Kill mid-recording: startup recovery stamps counts and status."""
    recorder.start_recorder("CRASH")
    _feed_prints("CRASH", 6)
    session_dir = _session_dir()

    # Simulate SIGKILL: process globals vanish, nothing is flushed or finalized,
    # and the active-session marker is left on disk.
    recorder._crash_for_tests()
    bar_buckets.reset_for_tests()
    assert (_capture_root / ".active_session.json").is_file()
    assert _manifest(session_dir).get("stopped_et") is None

    summary = session_state.finalize_orphaned_session(_capture_root)

    assert summary is not None
    man = _manifest(session_dir)
    assert man["status"] == CAPTURE_STATUS_INTERRUPTED
    assert man["stopped_et"]
    assert man["counts"]["prints"] == 6
    assert not (_capture_root / ".active_session.json").exists(), "marker not consumed"
    assert recorder.status()["interrupted_session"]["symbol"] == "CRASH"


def test_resume_after_interruption_keeps_recovered_counts(_capture_root) -> None:
    recorder.start_recorder("RESUME")
    _feed_prints("RESUME", 4)
    session_dir = _session_dir()
    recorder._crash_for_tests()
    bar_buckets.reset_for_tests()
    session_state.finalize_orphaned_session(_capture_root)

    recorder.start_recorder("RESUME")
    _feed_prints("RESUME", 2, start_ts=1_700_300_000.0)
    _stop_within()

    man = _manifest(session_dir)
    rows_on_disk = sum(
        1 for line in (session_dir / "prints.jsonl").read_text(encoding="utf-8").splitlines() if line
    )
    assert man["counts"]["prints"] == rows_on_disk == 6


def test_clean_stop_leaves_no_orphan_marker(_capture_root) -> None:
    recorder.start_recorder("CLEAN")
    _feed_prints("CLEAN", 2)
    _stop_within()

    assert not (_capture_root / ".active_session.json").exists()
    assert session_state.finalize_orphaned_session(_capture_root) is None


def test_torn_tail_is_counted_and_reported(_capture_root, caplog) -> None:
    prints = _capture_root / "prints.jsonl"
    prints.write_text('{"a":1}\n{"a":2}\n{"a":3', encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        rows, torn = manifest_io.count_rows(prints)

    assert (rows, torn) == (2, True)
    assert any("torn tail" in r.getMessage() for r in caplog.records)


# --------------------------------------------------------------------------
# D-068 -- a failed write is loud, and ends the session visibly
# --------------------------------------------------------------------------


class _FullDisk:
    """Stand-in for a stream on a full disk / removed drive."""

    def __init__(self) -> None:
        self.closed = False

    def write(self, _data: str) -> int:
        raise OSError(28, "No space left on device")

    def flush(self) -> None:
        raise OSError(28, "No space left on device")

    def fileno(self) -> int:
        raise OSError(28, "No space left on device")

    def close(self) -> None:
        self.closed = True


def _break_prints_stream() -> _FullDisk:
    broken = _FullDisk()
    recorder._primary().files["prints"] = broken
    return broken


def test_write_failure_is_logged_at_warning_or_higher(caplog) -> None:
    """D-068: ENOSPC produced no log line anywhere — root is INFO."""
    recorder.start_recorder("ENOSPC")
    _break_prints_stream()

    with caplog.at_level(logging.WARNING):
        recorder.record_print({"symbol": "ENOSPC", "ts": 1.0, "price": 1.0, "size": 1})

    assert [r for r in caplog.records if r.levelno >= logging.WARNING], (
        "a failed capture write produced no WARNING+ record"
    )
    _stop_within()


def test_write_failure_does_not_raise_into_the_tape_path() -> None:
    """One failed write used to abort quotes, L2 and bars for the whole tick."""
    recorder.start_recorder("NORAISE")
    _break_prints_stream()

    recorder.record_print({"symbol": "NORAISE", "ts": 1.0, "price": 1.0, "size": 1})
    recorder.record_quote({"symbol": "NORAISE", "ts": 1.0, "bid": 1.0, "ask": 1.1})

    assert recorder.status()["counts"]["quotes"] == 1, "a print failure killed the quote stream"
    _stop_within()


def test_repeated_write_failures_stop_the_session_and_surface_the_error() -> None:
    recorder.start_recorder("GIVEUP")
    session_dir = _session_dir()
    _break_prints_stream()

    for _ in range(CAPTURE_MAX_WRITE_FAILURES):
        recorder.record_print({"symbol": "GIVEUP", "ts": 1.0, "price": 1.0, "size": 1})

    status = recorder.status()
    assert status["recording"] is False, "recorder kept reporting itself healthy"
    assert "No space left on device" in (status["error"] or "")
    assert _manifest(session_dir)["status"] == CAPTURE_STATUS_FAILED


def test_api_status_goes_red_with_error_after_a_write_failure() -> None:
    """/api/capture must stop answering ``capture: true`` (D-068)."""
    mode.set_capture_mode(True, symbol="APIFAIL")
    assert mode.status_payload()["capture"] is True
    _break_prints_stream()

    for _ in range(CAPTURE_MAX_WRITE_FAILURES):
        recorder.record_print({"symbol": "APIFAIL", "ts": 1.0, "price": 1.0, "size": 1})

    payload = mode.status_payload()
    assert payload["capture"] is False
    assert "No space left on device" in (payload.get("error") or "")


def test_healthy_writes_record_a_last_write_timestamp() -> None:
    """A stalled recording is detectable even when nothing raises (D-068/4)."""
    recorder.start_recorder("STALL")
    assert recorder.status()["last_write_ts"] is None

    recorder.record_print({"symbol": "STALL", "ts": 1.0, "price": 1.0, "size": 1})

    assert recorder.status()["last_write_ts"] is not None
    assert recorder.status()["write_failures"] == 0
    _stop_within()


# --------------------------------------------------------------------------
# D-075 -- basic contract coverage the package never had
# --------------------------------------------------------------------------


def test_record_calls_while_not_recording_are_ignored() -> None:
    recorder.record_print({"symbol": "OFF", "ts": 1.0, "price": 1.0, "size": 1})
    recorder.record_bar("1m", {"symbol": "OFF", "ts": 1.0})
    assert recorder.is_recording() is False


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("10Sec", "bars_10s"),
        ("1Min", "bars_1m"),
        ("5 Min", "bars_5m"),
        ("1Day", "bars_1d"),
        ("daily", "bars_1d"),
    ],
)
def test_bar_timeframe_normalisation(given: str, expected: str) -> None:
    recorder.start_recorder("TF")
    recorder.record_bar(given, {"symbol": "TF", "ts": 1.0, "close": 1.0})
    assert recorder.status()["counts"][expected] == 1
    _stop_within()


def test_unknown_bar_timeframe_is_warned_and_skipped(caplog) -> None:
    recorder.start_recorder("TFBAD")
    with caplog.at_level(logging.WARNING):
        recorder.record_bar("7m", {"symbol": "TFBAD", "ts": 1.0})
    assert any("unknown bar timeframe" in r.getMessage() for r in caplog.records)
    assert sum(recorder.status()["counts"].values()) == 0
    _stop_within()


def test_capture_root_honours_the_env_override(_capture_root) -> None:
    assert recorder.capture_root() == _capture_root


def test_drain_open_returns_bars_without_touching_the_recorder() -> None:
    """bar_buckets must stay a pure producer — that callback was D-063."""
    bar_buckets.on_print("PURE", 1_700_000_000.0, 5.0, 10.0, source="sim", session_date="2026-09-20")
    drained = bar_buckets.drain_open("PURE")

    assert {tf for tf, _ in drained} == {"10s", "1m", "5m", "1d"}
    assert bar_buckets.drain_open("PURE") == [], "buckets were not popped"
    assert not hasattr(bar_buckets, "flush_open"), "the re-entrant callback is back"


# --------------------------------------------------------------------------
# Segments carry why they ended (operator decision, 2026-09-21)
# --------------------------------------------------------------------------


def test_segments_carry_the_reason_they_ended() -> None:
    recorder.start_recorder("WHY")
    _feed_prints("WHY", 3)
    _stop_within()
    assert _manifest()["segments"][-1]["reason"] == "operator"
    recorder.start_recorder("WHY")
    _feed_prints("WHY", 2, start_ts=1_700_000_100.0)
    recorder.fail_recorder("disk gone")
    man = _manifest()
    assert man["status"] == CAPTURE_STATUS_FAILED
    assert [seg["reason"] for seg in man["segments"]] == ["operator", "failure"]
    assert man["segments"][-1]["counts"]["prints"] == 2


def test_a_restart_stamps_a_restart_segment_with_its_own_counts(_capture_root) -> None:
    recorder.start_recorder("CRASH")
    _feed_prints("CRASH", 3)
    _stop_within()
    recorder.start_recorder("CRASH")
    _feed_prints("CRASH", 6, start_ts=1_700_000_100.0)
    session_dir = _session_dir()
    recorder._crash_for_tests()
    bar_buckets.reset_for_tests()

    summary = session_state.finalize_orphaned_session(_capture_root)

    man = _manifest(session_dir)
    assert [seg["reason"] for seg in man["segments"]] == ["operator", "restart"]
    assert man["segments"][-1]["status"] == CAPTURE_STATUS_INTERRUPTED
    assert man["segments"][-1]["counts"]["prints"] == 6      # this segment, not the day
    assert man["counts"]["prints"] == 9                      # the day
    assert summary["session_date"] == session_dir.parent.name
    assert summary["last_write_ts"] is not None
    assert recorder.status()["interrupted_session"]["symbol"] == "CRASH"


def test_status_says_which_segment_and_when_the_session_began() -> None:
    recorder.start_recorder("SEG")
    _feed_prints("SEG", 1)
    first = recorder.status()
    assert first["segment"] == 1 and first["started_et"] == first["segment_started_et"]
    _stop_within()
    recorder.start_recorder("SEG")
    second = recorder.status()
    assert second["segment"] == 2
    assert second["started_et"] == first["started_et"]      # the session, carried across
    assert second["segment_started_et"] != first["segment_started_et"]


def test_segment_summary_counts_the_gaps_between_segments() -> None:
    from capture.sessions import segment_summary

    segments = [
        {"started_et": "2026-09-21T09:30:00-04:00", "stopped_et": "2026-09-21T09:40:00-04:00", "reason": "failure"},
        {"started_et": "2026-09-21T09:42:00-04:00", "stopped_et": "2026-09-21T09:50:00-04:00", "reason": "restart"},
        {"started_et": "2026-09-21T09:55:00-04:00", "stopped_et": "2026-09-21T10:00:00-04:00", "reason": "operator"},
    ]
    assert segment_summary(segments) == {"segments": 3, "missing_sec": 7 * 60, "last_reason": "operator"}
    assert segment_summary(None) == {"segments": 0, "missing_sec": 0, "last_reason": None}
    overlapping = segments[:1] + [{"started_et": "2026-09-21T09:35:00-04:00", "stopped_et": "2026-09-21T09:45:00-04:00"}]
    assert segment_summary(overlapping)["missing_sec"] == 0
