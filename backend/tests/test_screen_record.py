"""The trading screen recording (ADR 035): the desktop app reports, the checklist fails loudly when the screen is not recorded."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from constants_diagnostics import DIAG_STATE_FAIL, DIAG_STATE_OFF, DIAG_STATE_OK, DIAG_STATE_WARN
from constants_screen_record import SCREEN_RECORD_STALE_SEC
from diagnostics.collect_screen_record import screen_record_rows
from main import app
from screen_record import store

client = TestClient(app)
GB = 1024**3


@pytest.fixture(autouse=True)
def fresh():
    store.reset_for_tests()
    yield
    store.reset_for_tests()


def report(**over):
    body = {
        "schema_version": 1, "state": "recording", "recording": True, "since": 1790257440.0, "error": None,
        "dir": "F:\\Nova\\screen", "dir_source": "data_drive", "dir_note": None, "dir_error": None,
        "mime": "video/x-matroska;codecs=avc1", "fps": 15, "segment_min": 15,
        "displays": [
            {"index": 1, "count": 2, "id": "11", "label": "left", "primary": False, "scale_factor": 1.5,
             "width": 2560, "height": 1440, "recording": True, "since": 1790257440.0,
             "file": "094400-screen1.mkv", "bytes": 1000, "last_data_ts": 1790257500.0, "error": None, "retry_at": None},
            {"index": 2, "count": 2, "id": "22", "label": "main", "primary": True, "scale_factor": 1,
             "width": 1920, "height": 1080, "recording": True, "since": 1790257440.0,
             "file": "094400-screen2.mkv", "bytes": 1000, "last_data_ts": 1790257500.0, "error": None, "retry_at": None},
        ],
        "unmatched": [],
        "disk": {"free_bytes": 800 * GB, "state": "ok", "error": None, "checked_ts": 1790257440.0},
        "problems": [], "restarts": 0, "generated_at": 1790257500.0,
    }
    body.update(over)
    return body


def the_row(status):
    rows = screen_record_rows(status=status)
    assert len(rows) == 1
    return rows[0]


def test_post_then_get_keeps_the_apps_own_report():
    assert client.get("/api/screen-record").json()["reported"] is False
    assert client.post("/api/screen-record", json=report()).json() == {"ok": True}
    got = client.get("/api/screen-record").json()
    assert got["reported"] is True and got["fresh"] is True
    assert got["report"]["displays"][0]["file"] == "094400-screen1.mkv"
    assert got["report"]["segment_min"] == 15  # fields the model does not name are kept


@pytest.mark.parametrize("bad", [
    {"schema_version": 2},
    {"state": "maybe"},
    {"dir_source": "somewhere"},
    {"displays": [{"index": 0, "recording": True, "width": 1, "height": 1}]},
])
def test_post_refuses_what_it_does_not_know(bad):
    res = client.post("/api/screen-record", json=report(**bad))
    assert res.status_code == 422
    assert client.get("/api/screen-record").json()["reported"] is False


def test_post_refuses_a_body_that_is_not_a_report():
    assert client.post("/api/screen-record", content=b"not json").status_code == 422
    assert client.post("/api/screen-record", json=[1, 2]).status_code == 422
    assert client.post("/api/screen-record", content=b"x" * (70 * 1024)).status_code == 413


def test_no_desktop_app_is_a_failure_not_a_blank():
    row = the_row(store.status())
    assert row["id"] == "screen_recorder" and row["group"] == "recorder"
    assert row["state"] == DIAG_STATE_FAIL
    assert "no Nova desktop app has reported" in row["detail"]
    assert "desktop app" in row["fix"]


def test_a_stale_report_is_a_failure():
    now = time.time()
    store.record(report(), now=now - SCREEN_RECORD_STALE_SEC - 5)
    row = the_row(store.status(now))
    assert row["state"] == DIAG_STATE_FAIL
    assert "last report is" in row["detail"]


def test_every_monitor_recording_is_ok():
    store.record(report())
    row = the_row(store.status())
    assert row["state"] == DIAG_STATE_OK
    assert row["detail"] == "recording 2 monitors to F:\\Nova\\screen (H.264, 15 fps)"
    assert row["since"] == 1790257440.0
    assert row["evidence"]["displays"][1] == {"index": 2, "recording": True, "width": 1920, "height": 1080, "error": None}


def test_a_monitor_not_recording_fails_with_the_reason():
    displays = report()["displays"]
    displays[1] = {**displays[1], "recording": False, "error": "NotReadableError: Could not start video source"}
    store.record(report(state="partial", recording=False, displays=displays))
    row = the_row(store.status())
    assert row["state"] == DIAG_STATE_FAIL
    assert row["detail"] == "only 1 of 2 monitors are recorded: NotReadableError: Could not start video source"


def test_a_failed_recorder_fails():
    store.record(report(state="failed", recording=False, error="the recorder process ended (crashed)",
                        displays=[{**report()["displays"][0], "recording": False}]))
    row = the_row(store.status())
    assert row["state"] == DIAG_STATE_FAIL
    assert row["detail"] == "the screen is not being recorded: the recorder process ended (crashed)"


def test_sleep_is_off_and_starting_is_a_warning():
    store.record(report(state="suspended", recording=False))
    assert the_row(store.status())["state"] == DIAG_STATE_OFF
    store.record(report(state="starting", recording=False))
    assert the_row(store.status())["state"] == DIAG_STATE_WARN


def test_the_system_drive_warns():
    store.record(report(dir="C:\\Users\\op\\AppData\\Roaming\\nova\\screen", dir_source="fallback",
                        dir_note="F: is not mounted, so the screen records to the system drive"))
    row = the_row(store.status())
    assert row["state"] == DIAG_STATE_WARN
    assert row["detail"].endswith("-- on the system drive")
    assert row["cause"] == "F: is not mounted, so the screen records to the system drive"


@pytest.mark.parametrize("free, state", [(40 * GB, DIAG_STATE_WARN), (5 * GB, DIAG_STATE_FAIL)])
def test_a_filling_drive_makes_the_row_worse(free, state):
    store.record(report(disk={"free_bytes": free, "state": "warn", "error": None}))
    row = the_row(store.status())
    assert row["state"] == state
    assert row["detail"].startswith("F: has ")


def test_the_drive_never_makes_a_failure_look_better():
    store.record(report(state="failed", recording=False, error="gone", disk={"free_bytes": 40 * GB}))
    row = the_row(store.status())
    assert row["state"] == DIAG_STATE_FAIL
    assert row["detail"].startswith("the screen is not being recorded: gone")


def test_the_checklist_carries_the_row():
    store.record(report())
    rows = client.get("/api/diagnostics").json()["rows"]
    assert [r["state"] for r in rows if r["id"] == "screen_recorder"] == [DIAG_STATE_OK]
