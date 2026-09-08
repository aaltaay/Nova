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


def test_parse_issue_rejects_bad_title(gh):
    assert gh.parse_issue({"number": 1, "title": "Random bug", "labels": []}) is None


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


def test_next_id_from_issue_rows(gh):
    assert gh.next_id_from_issues([{"id": "D-040"}, {"id": "D-008"}]) == "D-041"
    assert gh.next_id_from_issues([]) == "D-001"


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


def test_live_index_has_seed_ids(gh):
    items = gh.load_index()
    ids = {e["id"] for e in items}
    assert "D-001" in ids
    assert "D-011" in ids
    assert "D-040" in ids
    assert gh.next_id_from_issues(items) == "D-041"
