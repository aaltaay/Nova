"""Tests for tools/deferred_log.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "tools" / "deferred_log.py"

SAMPLE = """# Deferred log

<!-- OPEN_START -->

## D-002 -- Afterhours gap lie

- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** S

## D-010 -- Desk cannot place

- **Status:** open
- **Kind:** bug
- **Severity:** P0
- **Effort:** M

## D-003 -- Nice font

- **Status:** parked
- **Kind:** feature
- **Severity:** P3
- **Effort:** S

<!-- OPEN_END -->

<!-- CLOSED_START -->

## D-001 -- Old news gap

- **Status:** done
- **Kind:** bug
- **Severity:** P1

<!-- CLOSED_END -->
"""


def _load():
    spec = importlib.util.spec_from_file_location("deferred_log", MODULE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["deferred_log"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dl():
    return _load()


def test_parse_open_and_sort_severity(dl):
    items = dl.open_actionable(dl.parse_entries(SAMPLE, section="OPEN"))
    assert [e["id"] for e in items] == ["D-010", "D-002", "D-003"]
    assert items[0]["title"] == "Desk cannot place"


def test_closed_not_in_open(dl):
    closed = dl.parse_entries(SAMPLE, section="CLOSED")
    assert [e["id"] for e in closed] == ["D-001"]
    assert "D-001" not in [e["id"] for e in dl.parse_entries(SAMPLE, section="OPEN")]


def test_next_id_is_gone(dl):
    """Allocation raced; GitHub mints #NNN atomically instead."""
    assert not hasattr(dl, "next_id")


def test_open_actionable_survives_a_non_legacy_id(dl):
    """A `#NNN` id must not crash the sort -- this path feeds the sessionStart brief."""
    items = dl.open_actionable(
        [
            {"id": "#216", "title": "Human-filed", "severity": "P1", "status": "parked",
             "kind": "feature", "number": "216"},
            {"id": "D-011", "title": "Legacy", "severity": "P0", "status": "open",
             "kind": "bug", "number": "39"},
            {"id": "#?", "title": "No number at all", "severity": "P1", "status": "open",
             "kind": "bug", "number": ""},
        ]
    )
    assert [e["id"] for e in items] == ["D-011", "#216", "#?"]


def test_session_brief_survives_a_non_legacy_id(dl):
    lines = dl.format_session_brief_items(
        dl.open_actionable(
            [
                {"id": "#216", "title": "Human-filed", "severity": "P1",
                 "status": "open", "kind": "feature", "number": "216"}
            ]
        )
    )
    assert any("#216" in line for line in lines)


def test_session_brief_lists_p0_p1_only(dl):
    lines = dl.format_session_brief_lines(SAMPLE, top_n=3)
    blob = "\n".join(lines)
    assert "D-010" in blob
    assert "D-002" in blob
    assert "D-003" not in blob
    assert blob.startswith("Deferred (3 open):")


def test_session_brief_p2_only_summarizes(dl):
    text = """
<!-- OPEN_START -->
## D-004 -- Edge case
- **Status:** open
- **Kind:** bug
- **Severity:** P2
<!-- OPEN_END -->
<!-- CLOSED_START -->
<!-- CLOSED_END -->
"""
    lines = dl.format_session_brief_lines(text)
    assert lines == ["Deferred: 1 open (highest P2) -- deferred tracker"]


def test_session_brief_empty(dl):
    text = """
<!-- OPEN_START -->
<!-- OPEN_END -->
<!-- CLOSED_START -->
<!-- CLOSED_END -->
"""
    assert dl.format_session_brief_lines(text) == []


def test_cli_status_and_priorities(dl, tmp_path, capsys):
    path = tmp_path / "DEFERRED_LOG.md"
    path.write_text(SAMPLE, encoding="utf-8")
    assert dl.main(["status", "--path", str(path)]) == 0
    out = capsys.readouterr().out
    assert "D-010" in out
    assert dl.main(["priorities", "--path", str(path)]) == 0
    assert "D-010" in capsys.readouterr().out


def test_cli_rejects_next_id(dl, tmp_path):
    path = tmp_path / "DEFERRED_LOG.md"
    path.write_text(SAMPLE, encoding="utf-8")
    with pytest.raises(SystemExit):
        dl.main(["next-id", "--path", str(path)])


def test_prose_marker_mention_does_not_steal_closed_section(dl):
    text = """How-to: move it below `<!-- CLOSED_START -->` when done.

<!-- OPEN_START -->
## D-002 -- Still open
- **Status:** open
- **Kind:** bug
- **Severity:** P1
<!-- OPEN_END -->

<!-- CLOSED_START -->
## D-001 -- Finished
- **Status:** done
- **Kind:** bug
- **Severity:** P1
<!-- CLOSED_END -->
"""
    open_ids = [e["id"] for e in dl.parse_entries(text, section="OPEN")]
    closed_ids = [e["id"] for e in dl.parse_entries(text, section="CLOSED")]
    assert open_ids == ["D-002"]
    assert closed_ids == ["D-001"]


def test_format_status_includes_github_number(dl):
    items = [
        {
            "id": "D-011",
            "title": "Lock gap",
            "kind": "bug",
            "severity": "P0",
            "status": "open",
            "number": "12",
        }
    ]
    blob = dl.format_status_items(dl.open_actionable(items))
    assert "D-011 #12 Lock gap" in blob


def test_format_status_does_not_repeat_a_github_id(dl):
    """When the id already is `#216`, do not render `#216 #216`."""
    items = [
        {
            "id": "#216",
            "title": "Human-filed",
            "kind": "feature",
            "severity": "P2",
            "status": "open",
            "number": "216",
        }
    ]
    blob = dl.format_status_items(dl.open_actionable(items))
    assert "#216 Human-filed" in blob
    assert "#216 #216" not in blob


def test_live_file_points_at_github(dl):
    text = dl.DEFAULT_PATH.read_text(encoding="utf-8")
    assert "github.com/aaltaay/Nova/issues" in text
    assert "label:deferred" in text or "label `deferred`" in text or "label: `deferred`" in text
