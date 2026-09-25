"""/api/health names the revision this API process runs (the desk's title shows it beside its own)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from diagnostics import checkout_revision, process_info
from main import app


def test_health_carries_the_process_revision(monkeypatch):
    monkeypatch.setitem(process_info.REVISION, "release_tag", "v1006")
    body = TestClient(app).get("/api/health").json()
    assert body["release_tag"] == "v1006"
    assert body["instance_id"] and body["pid"]


def test_an_unknown_revision_is_null_never_a_guess(monkeypatch):
    monkeypatch.setitem(process_info.REVISION, "release_tag", None)
    assert TestClient(app).get("/api/health").json()["release_tag"] is None


def test_health_says_what_a_restart_would_load(monkeypatch):
    """The process runs v1017; its checkout on disk is v1024 after a pull (operator report 2026-09-25)."""
    monkeypatch.setitem(process_info.REVISION, "release_tag", "v1017")
    monkeypatch.setattr(checkout_revision, "checkout_tag", lambda: "v1024")
    body = TestClient(app).get("/api/health").json()
    assert body["release_tag"] == "v1017"
    assert body["checkout_tag"] == "v1024"


def test_an_unknown_checkout_is_null(monkeypatch):
    monkeypatch.setattr(checkout_revision, "checkout_tag", lambda: None)
    assert TestClient(app).get("/api/health").json()["checkout_tag"] is None
