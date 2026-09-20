"""Recorder boundary contracts; real writes always stay in a temporary root."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from capture import bar_buckets, recorder, session_state
from capture.constants_capture import CAPTURE_L2_MAX_HZ


@pytest.fixture(autouse=True)
def capture_root(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(tmp_path))
    recorder.reset_for_tests()
    bar_buckets.reset_for_tests()
    session_state.reset_for_tests()
    yield tmp_path
    recorder.reset_for_tests()
    bar_buckets.reset_for_tests()
    session_state.reset_for_tests()


def test_l2_throttle_retains_first_then_next_eligible_snapshot(capture_root, monkeypatch):
    # Patch this module's clock reference, never the process-wide time module.
    clock = SimpleNamespace(monotonic=lambda: 100.0, time=lambda: 1_700_000_000.0)
    monkeypatch.setattr(recorder, "time", clock)
    recorder.start_recorder("L2TEST")
    recorder.record_l2({"symbol": "L2TEST", "bids": [[10, 1]]})
    clock.monotonic = lambda: 100.0 + 0.5 / CAPTURE_L2_MAX_HZ
    recorder.record_l2({"symbol": "L2TEST", "bids": [[11, 2]]})
    clock.monotonic = lambda: 100.0 + 1.1 / CAPTURE_L2_MAX_HZ
    recorder.record_l2({"symbol": "L2TEST", "bids": [[12, 3]]})
    assert recorder.status()["counts"]["l2"] == 2
    path = next(capture_root.glob("*/L2TEST/l2.jsonl"))
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["bids"] for row in rows] == [[[10, 1]], [[12, 3]]]


def test_capture_root_falls_back_to_isolated_cache(tmp_path, monkeypatch):
    from capture import constants_capture

    monkeypatch.delenv("NOVA_SIM_CAPTURE_DIR")
    # A relative path has no Windows drive, so this never probes the operator disk.
    monkeypatch.setattr(constants_capture, "DEFAULT_SIM_CAPTURE_ROOT_WIN", "no-drive")
    monkeypatch.setattr(recorder, "cache_dir", lambda: tmp_path / "cache")
    assert recorder.capture_root() == tmp_path / "cache" / "sim_capture"
    assert recorder.capture_root().is_dir()


def test_inactive_recorders_do_not_create_streams(capture_root):
    recorder.record_print({"price": 10})
    recorder.record_quote({"bid": 9, "ask": 11})
    recorder.record_l2({"bids": [[9, 1]], "asks": [[11, 1]]})
    recorder.record_bar("1m", {"close": 10})
    assert not list(capture_root.rglob("*.jsonl"))
