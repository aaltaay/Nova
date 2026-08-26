"""Tests for Graphify usage meter (honest cited-note savings)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
USAGE_PATH = REPO_ROOT / "tools" / "graphify_usage.py"


def _load():
    spec = importlib.util.spec_from_file_location("graphify_usage", USAGE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["graphify_usage"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def usage():
    return _load()


SAMPLE_STDOUT = """\
Traversal: BFS depth=2 | Start: ['Graphify Knowledge Graph'] | 2 nodes found
NODE Graphify Knowledge Graph [src=knowledge/obsidian/00-System/Graphify-Knowledge-Graph.md loc= community=Memory]
NODE Other Note [src=None loc= community=Memory]
EDGE Graphify Knowledge Graph --references [EXTRACTED]--> Other Note
"""


def test_tokens_from_text_uses_four_chars(usage):
    assert usage.tokens_from_text("abcd") == 1
    assert usage.tokens_from_text("abcde") == 2
    assert usage.tokens_from_text("") == 0


def test_parse_source_paths_skips_none(usage):
    paths = usage.parse_source_paths(SAMPLE_STDOUT)
    assert paths == ["knowledge/obsidian/00-System/Graphify-Knowledge-Graph.md"]


def test_avoided_tokens_sums_cited_files_only(usage, tmp_path):
    note = tmp_path / "note.md"
    note.write_text("x" * 40, encoding="utf-8")
    avoided = usage.avoided_tokens(["note.md", "missing.md"], tmp_path)
    assert avoided == 10  # 40 chars / 4


def test_record_event_saves_avoided_minus_used(usage, tmp_path):
    note = tmp_path / "a.md"
    note.write_text("n" * 80, encoding="utf-8")
    store = tmp_path / "usage.json"
    event = usage.record_event(
        command="query",
        question="what connects memory?",
        stdout="NODE A [src=a.md loc=]",
        repo_root=tmp_path,
        store_path=store,
    )
    assert event["used_tokens"] == usage.tokens_from_text("NODE A [src=a.md loc=]")
    assert event["avoided_tokens"] == 20
    assert event["saved_tokens"] == max(0, 20 - event["used_tokens"])
    payload = json.loads(store.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["query_count"] == 1
    assert payload["total_saved_tokens"] == event["saved_tokens"]


def test_record_event_zero_saved_when_no_cited_files(usage, tmp_path):
    store = tmp_path / "usage.json"
    event = usage.record_event(
        command="query",
        question="unknown",
        stdout="NODE Ghost [src=None loc=]",
        repo_root=tmp_path,
        store_path=store,
    )
    assert event["avoided_tokens"] == 0
    assert event["saved_tokens"] == 0


def test_format_footer_is_machine_readable(usage):
    event = {
        "used_tokens": 10,
        "avoided_tokens": 50,
        "saved_tokens": 40,
    }
    totals = {"query_count": 3, "total_saved_tokens": 90}
    line = usage.format_footer(event, totals)
    assert line.startswith("graphify_usage ")
    assert "used=10" in line
    assert "avoided=50" in line
    assert "saved=40" in line
    assert "queries=3" in line
    assert "total_saved=90" in line


def test_status_line_zero_when_missing(usage, tmp_path):
    line = usage.format_status(usage.load_usage(tmp_path / "missing.json"))
    assert "queries=0" in line
    assert "total_saved=0" in line
