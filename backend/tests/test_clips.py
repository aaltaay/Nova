"""Share clips (ADR 039): the desktop app reports its clip view; the checklist is quiet unless a clip has no picture."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clips import store
from constants_clips import CLIPS_STALE_SEC
from constants_diagnostics import DIAG_STATE_FAIL, DIAG_STATE_OFF, DIAG_STATE_OK, DIAG_STATE_UNKNOWN, DIAG_STATE_WARN
from diagnostics.collect_clips import clip_rows
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh():
    store.reset_for_tests()
    yield
    store.reset_for_tests()


def view(**over):
    body = {
        "schema_version": 1, "generated_at": 1790257500.0, "dir": "F:\\Nova\\clips", "dir_source": "data_drive",
        "dir_note": None, "dir_error": None, "skipped": 0, "hq_max": 2, "hq_in_use": 1, "hq_max_sec": 1800,
        "hq_warn_sec": 60, "last_n_sec": 300,
        "open": [{"clip_id": "clip-1", "symbol": "PFSA", "started_ts": 1790257428.0, "state": "ok", "reason": None,
                  "showing": None, "window_id": "main", "screen_recording": True,
                  "hq": {"since": 1790257428.0, "ends_at": 1790259228.0, "recording": True, "lost": False,
                         "error": None, "retry_at": None}}],
        "clips": [{"clip_id": "clip-1", "symbol": "PFSA", "status": "recording"},
                  {"clip_id": "clip-0", "symbol": "APUS", "status": "ready"}],
        "exporting": None, "queued": 0, "tabs": [], "disk": {"free_bytes": 790 * 1024**3, "state": "ok"},
    }
    body.update(over)
    return body


def the_row(status):
    rows = clip_rows(status=status)
    assert len(rows) == 1
    return rows[0]


def test_post_then_get_keeps_the_apps_own_view():
    assert client.get("/api/clips").json()["reported"] is False
    assert client.post("/api/clips", json=view()).json() == {"ok": True}
    got = client.get("/api/clips").json()
    assert got["reported"] is True and got["fresh"] is True
    assert got["view"]["open"][0]["symbol"] == "PFSA"
    assert got["view"]["last_n_sec"] == 300  # fields the model does not name are kept


def test_a_view_it_cannot_read_is_refused():
    assert client.post("/api/clips", json=view(schema_version=2)).status_code == 422
    assert client.post("/api/clips", json=view(dir_source="cloud")).status_code == 422
    bad = view(open=[{"clip_id": "x", "symbol": "PFSA", "started_ts": 1.0, "state": "exploded"}])
    assert client.post("/api/clips", json=bad).status_code == 422
    assert client.post("/api/clips", content=b"[1,2]", headers={"content-type": "application/json"}).status_code == 422
    assert client.post("/api/clips", content=b"x" * (300 * 1024), headers={"content-type": "application/json"}).status_code == 413
    assert client.get("/api/clips").json()["reported"] is False


def test_the_row_is_off_without_a_desktop_app_and_unknown_when_stale():
    assert the_row(store.status())["state"] == DIAG_STATE_OFF
    store.record(view(), now=1000.0)
    stale = the_row(store.status(now=1000.0 + CLIPS_STALE_SEC + 5))
    assert stale["state"] == DIAG_STATE_UNKNOWN
    assert "s old" in stale["detail"]


def test_the_row_is_quiet_while_clips_record():
    store.record(view())
    r = the_row(store.status())
    assert r["state"] == DIAG_STATE_OK
    assert "1 clip open (PFSA; 1 in high quality)" in r["detail"]
    assert r["evidence"]["open"] == [{"symbol": "PFSA", "state": "ok", "started_ts": 1790257428.0, "hq": True}]


def test_a_lost_capture_warns_and_no_picture_fails():
    lost = view(open=[{**view()["open"][0], "state": "hq_lost"}])
    store.record(lost)
    assert the_row(store.status())["state"] == DIAG_STATE_WARN
    blank = view(open=[{**view()["open"][0], "state": "no_picture", "hq": None}])
    store.record(blank)
    r = the_row(store.status())
    assert r["state"] == DIAG_STATE_FAIL
    assert "no picture" in r["detail"]


def test_the_system_drive_or_an_unwritable_list_warns():
    store.record(view(dir_source="fallback", dir_note="F: is not mounted, so clips go to the system drive"))
    assert the_row(store.status())["state"] == DIAG_STATE_WARN
    store.record(view(dir_error="the clip list could not be written: EACCES"))
    r = the_row(store.status())
    assert r["state"] == DIAG_STATE_WARN
    assert "NOVA_CLIPS_DIR" in r["fix"]


def test_the_checklist_carries_the_row():
    store.record(view())
    rows = client.get("/api/diagnostics").json()["rows"]
    assert any(r["id"] == "clips" and r["state"] == DIAG_STATE_OK for r in rows)
