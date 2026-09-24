"""The leaderboard keeps every day; its diagnostics row guards the drive instead (#485).

Operator decision 2026-09-24: no automatic deletion. ``leaderboard_recorder``
carries the store's size and its drive's free space, warns under 50 GB free and
fails under 10 GB; a size or free space it cannot read is ``unknown`` with the
reason, never ``ok``; the drive only ever makes the row worse.
"""
from __future__ import annotations

import re
from collections import namedtuple

import pytest

from constants_leaderboard import LEADERBOARD_FREE_FAIL_BYTES, LEADERBOARD_FREE_WARN_BYTES
from diagnostics import collect_leaderboard, gather as gather_mod
from leaderboard import recorder, store

GB = 1024**3
Usage = namedtuple("Usage", "total used free")
RECORDING = {"recording": True, "ok": True, "error": None, "since": None, "run_id": "r1"}


@pytest.fixture
def store_files():
    root = store.root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "leaderboard.sqlite3").write_bytes(b"x" * 3000)
    (root / "leaderboard.sqlite3-wal").write_bytes(b"x" * 1000)
    return root


def _row(monkeypatch, *, free: int | None = None, error: OSError | None = None, status: dict | None = None):
    seen: list[str] = []

    def usage(path):
        seen.append(str(path))
        if error is not None:
            raise error
        return Usage(2000 * GB, 2000 * GB - free, free)

    monkeypatch.setattr(recorder, "status", lambda: dict(status or RECORDING))
    monkeypatch.setattr(gather_mod.shutil, "disk_usage", usage)
    rows = collect_leaderboard.leaderboard_rows(**gather_mod._leaderboard_inputs())
    assert seen == [str(store.root())]
    return {r["id"]: r for r in rows}["leaderboard_recorder"]


def test_plenty_of_room_leaves_the_row_as_it_was(monkeypatch, store_files):
    row = _row(monkeypatch, free=851 * GB)
    assert row["state"] == "ok" and row["detail"] == "recording every scanner board once a minute"
    ev = row["evidence"]
    assert ev["store_bytes"] == 4000                 # the database plus its write-ahead log
    assert ev["free_bytes"] == 851 * GB and ev["disk_error"] is None
    assert ev["store"] == str(store.path())


@pytest.mark.parametrize("free, state", [
    (LEADERBOARD_FREE_WARN_BYTES, "ok"),
    (LEADERBOARD_FREE_WARN_BYTES - 1, "warn"),
    (42 * GB, "warn"),
    (LEADERBOARD_FREE_FAIL_BYTES, "warn"),
    (LEADERBOARD_FREE_FAIL_BYTES - 1, "fail"),
    (0, "fail"),
])
def test_free_space_warns_under_50_gb_and_fails_under_10(monkeypatch, store_files, free, state):
    row = _row(monkeypatch, free=free)
    assert row["state"] == state
    assert row["evidence"]["free_bytes"] == free
    if state != "ok":
        assert "free" in row["detail"] and "recording every scanner board" in row["detail"]
        assert "6-9 GB a year" in row["cause"] and "no automatic deletion" in row["cause"]
        assert "NOVA_LEADERBOARD_DIR" in row["fix"]


def test_the_warning_names_the_room_left(monkeypatch, store_files):
    row = _row(monkeypatch, free=42 * GB)
    # A Windows store is named by its drive letter ("C: has ..."); elsewhere by the folder holding it.
    assert re.match(r"^(the drive holding |[A-Za-z]: )", row["detail"]), row["detail"]
    assert "has 42 GB free (warns under 50 GB); the store is 0 MB" in row["detail"]


def test_unreadable_free_space_is_unknown_with_the_reason(monkeypatch, store_files):
    row = _row(monkeypatch, error=OSError(21, "The device is not ready"))
    assert row["state"] == "unknown"
    assert "The device is not ready" in row["detail"] and "The device is not ready" in row["cause"]
    assert row["evidence"]["free_bytes"] is None
    assert "The device is not ready" in row["evidence"]["disk_error"]
    assert row["evidence"]["store_bytes"] == 4000


def test_a_store_folder_that_is_not_there_is_unknown_not_ok(monkeypatch):
    monkeypatch.setattr(recorder, "status", lambda: dict(RECORDING))
    assert not store.root().exists()
    rows = collect_leaderboard.leaderboard_rows(**gather_mod._leaderboard_inputs())
    row = {r["id"]: r for r in rows}["leaderboard_recorder"]
    assert row["state"] == "unknown" and "FileNotFoundError" in row["detail"]
    assert row["evidence"]["store_bytes"] == 0 and row["evidence"]["free_bytes"] is None


def test_an_unreadable_size_is_unknown_with_the_reason():
    disk = {"store_bytes": None, "free_bytes": 800 * GB, "size_error": "PermissionError: denied", "free_error": None}
    [row, _auto] = collect_leaderboard.leaderboard_rows(
        recorder=dict(RECORDING), auto={}, store_path=r"F:\Nova\leaderboard\leaderboard.sqlite3", disk=disk)
    assert row["state"] == "unknown" and "PermissionError: denied" in row["detail"]
    assert row["evidence"]["disk_error"] == "PermissionError: denied"
    # Too little room still fails: an unknown size never hides it.
    disk["free_bytes"] = 5 * GB
    [row, _auto] = collect_leaderboard.leaderboard_rows(
        recorder=dict(RECORDING), auto={}, store_path=r"F:\Nova\leaderboard\leaderboard.sqlite3", disk=disk)
    assert row["state"] == "fail" and row["detail"].startswith("F: has 5.0 GB free (fails under 10 GB)")


@pytest.mark.parametrize("status, free, state", [
    ({**RECORDING, "ok": False, "error": "disk I/O error"}, 800 * GB, "fail"),   # a write failure stays a failure
    ({**RECORDING, "ok": False, "error": "disk I/O error"}, 20 * GB, "fail"),
    ({**RECORDING, "recording": False}, 800 * GB, "off"),                        # outside the session: still off
    ({**RECORDING, "recording": False}, 20 * GB, "warn"),
    ({**RECORDING, "recording": False, "run_id": None}, 800 * GB, "warn"),       # loop not started: still warn
    ({**RECORDING, "recording": False, "run_id": None}, 5 * GB, "fail"),
])
def test_the_drive_only_makes_the_row_worse(monkeypatch, store_files, status, free, state):
    row = _row(monkeypatch, free=free, status=status)
    assert row["state"] == state
    if not status["ok"]:
        assert row["detail"].startswith("cannot write the scanner board")
        if free < LEADERBOARD_FREE_WARN_BYTES:
            assert "20 GB free" in row["detail"]           # the drive is named beside the write failure
