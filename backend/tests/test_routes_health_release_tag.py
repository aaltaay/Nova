"""/api/health names the revision this API process runs (the desk's title shows it beside its own)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from diagnostics import process_info
from main import app


def test_health_carries_the_process_revision(monkeypatch):
    monkeypatch.setitem(process_info.REVISION, "release_tag", "v1006")
    body = TestClient(app).get("/api/health").json()
    assert body["release_tag"] == "v1006"
    assert body["instance_id"] and body["pid"]


def test_an_unknown_revision_is_null_never_a_guess(monkeypatch):
    monkeypatch.setitem(process_info.REVISION, "release_tag", None)
    assert TestClient(app).get("/api/health").json()["release_tag"] is None
