"""ADR 021 decision 1: GET /api/diagnostics is a checklist of facts, never a verdict."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from constants_diagnostics import DIAG_ENV_MISSING_PREFIX, DIAG_GROUPS, DIAG_STATES
from diagnostics import collect, gather as gather_mod, process_info
from diagnostics.routes import router

REQUIRED = {"id", "group", "title", "state", "detail", "cause", "fix", "since", "action", "evidence"}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _facts(**overrides):
    base = {
        "pid": 4242, "release_tag": "v900", "commit": "abc1234", "python": "3.13", "frozen": False,
        "repo_root": r"C:\Users\op\github\Nova", "worktree": False,
        "env_file": {"path": r"C:\Users\op\github\Nova\.env", "exists": True, "keys_loaded": 12, "keys": ["IBKR_ENABLED"], "override": False},
    }
    base.update(overrides)
    return base


def _by_id(rows):
    return {r["id"]: r for r in rows}


def test_every_row_carries_the_full_shape_and_the_counts_add_up():
    body = _client().get("/api/diagnostics").json()
    assert body["rows"], "the checklist is never empty"
    for r in body["rows"]:
        assert REQUIRED <= set(r), r["id"]
        assert r["state"] in DIAG_STATES
        assert r["group"] in {key for key, _label in DIAG_GROUPS}
        assert r["cause"] and r["fix"], r["id"]
    assert sum(body["counts"].values()) == len(body["rows"])


def test_a_worktree_rooted_api_is_named_as_such_with_the_fix():
    rows = _by_id(collect.process_rows(_facts(worktree=True, repo_root=r"C:\Nova\.claude\worktrees\agent-x")))
    root = rows["process_root"]
    assert root["state"] == "warn"
    assert "worktree" in root["detail"] and root["action"] is not None


def test_a_missing_env_file_is_a_failure_that_names_the_path_not_a_silent_off():
    missing = {"path": r"C:\Nova\.claude\worktrees\agent-x\.env", "exists": False, "keys_loaded": 0, "keys": [], "override": False}
    row = _by_id(collect.process_rows(_facts(env_file=missing)))["process_env_file"]
    assert row["state"] == "fail"
    assert row["detail"].startswith(DIAG_ENV_MISSING_PREFIX) and missing["path"] in row["detail"]


def test_env_facts_report_key_names_and_counts_never_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text("IBKR_ENABLED=true\nOPENAI_API_KEY=sk-secret-value\n", encoding="utf-8")
    facts = process_info.env_file_facts(env)
    assert facts["exists"] is True and facts["keys_loaded"] == 2
    assert "sk-secret-value" not in repr(facts)


def test_one_broken_collector_is_an_unknown_row_not_a_500(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("ledger unreadable")

    monkeypatch.setattr(collect, "practice_rows", boom)
    res = _client().get("/api/diagnostics")
    assert res.status_code == 200
    unknown = [r for r in res.json()["rows"] if r["state"] == "unknown" and "ledger unreadable" in r["detail"]]
    assert unknown, "the failure is stated as unknown with why"


def test_the_bundle_is_plain_text_for_copy_paste():
    res = _client().get("/api/diagnostics/bundle")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/plain")
    assert "Nova desk diagnostics" in res.text and "## Process" in res.text
    assert gather_mod.gather()["schema_version"] >= 1
