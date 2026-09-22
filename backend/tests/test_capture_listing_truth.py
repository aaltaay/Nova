"""Session Record listing and recorder truth (QA 2026-09-22, fix/qa-sim-replay).

C21 synthetic SIM1 is never a recording; C22 a running recording reads its live
counts and open segment; C41 the restart finalizer ends a dead segment at its
last write; C64 deliberate stops are not "missing"; C55 each recording's error
is its own; R13 data past the last segment is listed; R25 a print-less failed
session is not replayable.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from capture import bar_buckets, mode, recorder, session_state, sessions
from capture.constants_capture import CAPTURE_NO_PRINTS_REASON, CAPTURE_NOT_IBKR_REASON
from capture.segments import missing_seconds, recorded_segments

DAY = "2026-09-21"


def _iso(hms: str) -> str:
    return f"{DAY}T{hms}-04:00"


def _ts(hms: str) -> float:
    return datetime.fromisoformat(_iso(hms)).timestamp()


@pytest.fixture(autouse=True)
def capture_root(tmp_path, monkeypatch):
    root = tmp_path / "sim_capture"
    root.mkdir()
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(root))
    monkeypatch.setattr(sessions, "capture_root", lambda: root)
    from capture import bridge_ibkr
    monkeypatch.setattr(bridge_ibkr, "admission_error", lambda symbol: None)
    bar_buckets.reset_for_tests()
    session_state.reset_for_tests()
    mode.reset_for_tests()
    recorder.reset_for_tests()
    yield root
    recorder.reset_for_tests()
    bar_buckets.reset_for_tests()
    session_state.reset_for_tests()
    mode.reset_for_tests()


def _session(root: Path, symbol: str, manifest: dict, *, prints: int = 3, quotes: int = 0,
             written: float | None = None) -> Path:
    directory = root / DAY / symbol
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if prints:
        (directory / "prints.jsonl").write_text(
            "".join(json.dumps({"ts": _ts("10:00:00") + i, "symbol": symbol, "price": 10.0, "size": 100}) + "\n"
                    for i in range(prints)), encoding="utf-8")
    if quotes:
        (directory / "quotes.jsonl").write_text(
            json.dumps({"ts": _ts("10:00:00"), "symbol": symbol, "bid": 9.9, "ask": 10.1, "last": None}) + "\n",
            encoding="utf-8")
    if written is not None:
        for name in ("prints", "quotes"):
            path = directory / f"{name}.jsonl"
            if path.exists():
                os.utime(path, (written, written))
    return directory


def _row(symbol: str) -> dict:
    return next(r for r in sessions.list_sessions()["tickers_by_day"][DAY] if r["symbol"] == symbol)


def _segment(start: str, stop: str, reason: str | None = "operator", status: str = "stopped_partial_ok") -> dict:
    return {"started_et": _iso(start), "stopped_et": _iso(stop), "status": status, "reason": reason}


def test_synthetic_sim1_is_listed_but_never_usable_or_loadable(capture_root, monkeypatch) -> None:
    _session(capture_root, "SIM1", {"source": "sim", "status": "generated_full_day", "counts": {"prints": 3}})
    row = _row("SIM1")
    assert row["usable"] is False and row["unavailable_reason"] == CAPTURE_NOT_IBKR_REASON
    from sim import capture_player
    monkeypatch.setattr(capture_player, "capture_root", lambda: capture_root)
    loaded = capture_player.load(DAY, "SIM1")
    assert loaded["ok"] is False and loaded["error"] == CAPTURE_NOT_IBKR_REASON


def test_a_session_whose_every_segment_failed_without_a_print_is_not_replayable(capture_root) -> None:
    failed = _segment("10:00:00", "10:00:30", reason="operator", status="failed")
    _session(capture_root, "QUIET", {"source": "ibkr", "status": "failed", "segments": [failed]}, prints=0, quotes=1)
    row = _row("QUIET")
    assert row["empty"] is False and row["usable"] is False
    assert row["unavailable_reason"] == CAPTURE_NO_PRINTS_REASON


def test_a_running_recording_reads_its_live_counts_and_open_segment(capture_root) -> None:
    recorder.start_recorder("LIVE")
    for i in range(4):
        recorder.record_print({"symbol": "LIVE", "ts": 1_700_000_000.0 + i, "price": 10.0, "size": 100})
    day = Path(recorder.status()["dir"]).parent.name
    row = next(r for r in sessions.list_sessions()["tickers_by_day"][day] if r["symbol"] == "LIVE")
    assert row["prints"] == 4, "the manifest has not counted a first segment yet; the recorder has"
    assert row["segments"] == 1 and row["status"] == "recording"
    assert len(row["spans"]) == 1


def test_the_restart_finalizer_ends_a_dead_segment_at_its_last_write(capture_root) -> None:
    recorder.start_recorder("CRASH")
    recorder.record_print({"symbol": "CRASH", "ts": 1_700_000_000.0, "price": 10.0, "size": 100})
    directory = Path(recorder.status()["dir"])
    recorder._crash_for_tests()
    bar_buckets.reset_for_tests()
    last_write = datetime.now().timestamp() - 3600  # the dead process last wrote an hour ago
    for path in directory.glob("*.jsonl"):
        os.utime(path, (last_write, last_write))
    session_state.finalize_orphaned_session(capture_root)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    stopped = datetime.fromisoformat(manifest["segments"][-1]["stopped_et"]).timestamp()
    assert abs(stopped - last_write) < 2, "the dead stretch before the restart is not recorded"
    assert manifest["recovered_et"] != manifest["segments"][-1]["stopped_et"]


def test_a_deliberate_stop_is_not_missing_time_but_a_failure_is() -> None:
    segments = [
        _segment("09:00:00", "09:30:00", reason="operator"),
        _segment("14:42:00", "15:00:00", reason="failure"),
        _segment("15:05:00", "15:10:00", reason="operator"),
    ]
    assert missing_seconds(segments) == 5 * 60


def test_data_written_past_the_last_segment_is_listed_and_uncounted(capture_root) -> None:
    manifest = {"source": "ibkr", "status": "interrupted", "counts": {"prints": 3},
                "segments": [_segment("10:00:00", "10:10:00", reason="restart", status="interrupted")]}
    directory = _session(capture_root, "GRML", manifest, written=_ts("10:40:00"))
    row = _row("GRML")
    assert row["prints"] == -1, "the manifest's count understates rows written after its last segment"
    assert row["segments"] == 2
    assert row["spans"][-1] == [int(_ts("10:10:00")), int(_ts("10:40:00"))]
    segments = recorded_segments(manifest, directory, live=False)
    assert segments[-1]["status"] == "unlisted"


def test_each_recording_names_its_own_error_and_a_start_never_carries_another(monkeypatch) -> None:
    from capture import bridge_ibkr, worker

    mode._symbols[:] = ["AAA", "BBB"]
    monkeypatch.setattr(mode, "_reconcile", lambda: None)
    monkeypatch.setattr(worker, "status", lambda: {"pending_batches": 0, "accepting": True, "error": None})
    health = {"AAA": {"healthy": False, "state": "stale", "error": "IBKR AllLast stale; no recent prints for AAA"},
              "BBB": {"healthy": True, "state": "live", "error": None}}
    monkeypatch.setattr(bridge_ibkr, "producer_health", lambda sym: dict(health[sym]))
    monkeypatch.setattr(bridge_ibkr, "book_health", lambda sym: {"note": None})
    monkeypatch.setattr(recorder, "status", lambda sym=None: {"segment_prints": 5, "error": None})
    payload = mode.status_payload()
    assert payload["errors"] == {"AAA": "IBKR AllLast stale; no recent prints for AAA"}
    assert payload["error"].endswith("for AAA")  # the legacy single value is unchanged
    reply = mode._own_reply_error(payload, enabled=True, symbol="BBB")
    assert "error" not in reply, "starting BBB must not report AAA's tape as BBB's failure"
    assert mode._own_reply_error(payload, enabled=True, symbol="AAA")["error"].endswith("for AAA")
