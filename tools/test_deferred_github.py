"""Tests for tools/deferred_github.py (no network)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "deferred_github.py"


def _load():
    spec = importlib.util.spec_from_file_location("deferred_github", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["deferred_github"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gh():
    return _load()


def test_parse_issue_maps_labels(gh):
    issue = {
        "number": 12,
        "title": "D-011 -- Broker send outside lock",
        "state": "OPEN",
        "url": "https://github.com/aaltaay/Nova/issues/12",
        "labels": [
            {"name": "deferred"},
            {"name": "P0"},
            {"name": "bug"},
            {"name": "domain:execution"},
            {"name": "blocked"},
        ],
    }
    parsed = gh.parse_issue(issue)
    assert parsed is not None
    assert parsed["id"] == "D-011"
    assert parsed["title"] == "Broker send outside lock"
    assert parsed["kind"] == "bug"
    assert parsed["severity"] == "P0"
    assert parsed["status"] == "blocked"
    assert parsed["number"] == "12"
    assert parsed["domain"] == "execution"


def test_parse_issue_feature_and_parked(gh):
    parsed = gh.parse_issue(
        {
            "number": 3,
            "title": "D-036 -- Follow-ups",
            "state": "OPEN",
            "labels": ["deferred", "P2", "enhancement", "parked"],
        }
    )
    assert parsed is not None
    assert parsed["kind"] == "feature"
    assert parsed["status"] == "parked"


def test_parse_issue_keeps_plain_title_under_github_number(gh):
    """A human-filed issue has the label but not the legacy `D-NNN --` format."""
    parsed = gh.parse_issue(
        {
            "number": 216,
            "title": "[Bot #205] 11/11 L3 Unrestricted (later)",
            "state": "OPEN",
            "labels": ["deferred", "P2", "enhancement", "parked"],
        }
    )
    assert parsed is not None, "a labeled issue must never be dropped for its title"
    assert parsed["id"] == "#216"
    assert parsed["title"] == "[Bot #205] 11/11 L3 Unrestricted (later)"
    assert parsed["status"] == "parked"
    assert parsed["number"] == "216"


def test_parse_issue_still_reads_legacy_prefix(gh):
    parsed = gh.parse_issue({"number": 39, "title": "D-011 -- Lock gap", "labels": []})
    assert parsed is not None
    assert parsed["id"] == "D-011"
    assert parsed["title"] == "Lock gap"


def test_parse_issue_rejects_empty_title(gh):
    assert gh.parse_issue({"number": 1, "title": "   ", "labels": []}) is None


def test_fetch_entries_warns_on_skipped(gh, monkeypatch, capsys):
    monkeypatch.setattr(
        gh,
        "list_issues",
        lambda **_k: [
            {"number": 1, "title": "", "state": "OPEN", "labels": ["deferred"]},
            {"number": 2, "title": "Real one", "state": "OPEN", "labels": ["deferred"]},
        ],
    )
    items = gh.fetch_entries(state="open")
    assert [e["id"] for e in items] == ["#2"]
    assert "1 `deferred` issue(s) skipped" in capsys.readouterr().err


def test_next_id_is_gone(gh):
    """Allocation raced; GitHub mints #NNN atomically instead."""
    assert not hasattr(gh, "next_id_from_issues")


def test_labels_for_entry(gh):
    labels = gh.labels_for_entry(
        {
            "kind": "decision",
            "severity": "P1",
            "status": "blocked",
            "domain": "execution | ibkr-ops",
        }
    )
    assert "deferred" in labels
    assert "P1" in labels
    assert "decision" in labels
    assert "blocked" in labels
    assert "domain:execution" in labels
    assert "domain:ibkr-ops" in labels


def test_index_round_trip_and_schema(gh, tmp_path):
    path = tmp_path / "deferred-index.json"
    items = [
        {
            "id": "D-011",
            "title": "Lock gap",
            "kind": "bug",
            "severity": "P0",
            "status": "open",
            "number": "39",
        }
    ]
    gh.write_index(items, path=path)
    loaded = gh.load_index(path)
    assert loaded[0]["id"] == "D-011"
    raw = path.read_text(encoding="utf-8")
    assert '"schema_version": 1' in raw


def test_fetch_entries_uses_index_when_gh_empty(gh, tmp_path, monkeypatch):
    path = tmp_path / "deferred-index.json"
    gh.write_index(
        [
            {
                "id": "D-011",
                "title": "Lock gap",
                "kind": "bug",
                "severity": "P0",
                "status": "open",
                "number": "39",
            }
        ],
        path=path,
    )
    monkeypatch.setattr(gh, "INDEX_PATH", path)
    monkeypatch.setattr(gh, "list_issues", lambda **_k: [])
    items = gh.fetch_entries(state="open")
    assert items[0]["id"] == "D-011"


def test_refresh_index_writes_live_issues(gh, tmp_path, monkeypatch):
    path = tmp_path / "deferred-index.json"
    monkeypatch.setattr(gh, "INDEX_PATH", path)
    monkeypatch.setattr(
        gh,
        "list_issues",
        lambda **_k: [
            {
                "number": 39,
                "title": "D-011 -- Lock gap",
                "state": "OPEN",
                "labels": ["deferred", "P0", "bug"],
            }
        ],
    )
    count, target = gh.refresh_index()
    assert count == 1
    assert target == str(path)
    assert gh.load_index(path)[0]["id"] == "D-011"


def test_refresh_index_refuses_to_erase_snapshot(gh, tmp_path, monkeypatch):
    path = tmp_path / "deferred-index.json"
    gh.write_index([{"id": "D-011", "title": "Lock gap", "status": "open"}], path=path)
    monkeypatch.setattr(gh, "INDEX_PATH", path)
    monkeypatch.setattr(gh, "list_issues", lambda **_k: [])
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        gh.refresh_index()
    assert gh.load_index(path)[0]["id"] == "D-011"


def test_refresh_index_seeds_empty_snapshot(gh, tmp_path, monkeypatch):
    path = tmp_path / "deferred-index.json"
    monkeypatch.setattr(gh, "INDEX_PATH", path)
    monkeypatch.setattr(gh, "list_issues", lambda **_k: [])
    count, _ = gh.refresh_index()
    assert count == 0
    assert gh.load_index(path) == []


def test_live_index_has_seed_ids(gh):
    items = gh.load_index()
    ids = {e["id"] for e in items}
    assert "D-001" in ids
    assert "D-011" in ids
    assert "D-040" in ids
