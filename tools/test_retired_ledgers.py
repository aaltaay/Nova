"""Retired ledgers must not be required or recreated by agent automation."""
from pathlib import Path

import pytest

from tools import changes_collate, changes_new
from tools.changes_fragments import ENTRIES_MARKER, render_fragment


def test_problem_fragment_command_refuses_before_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(changes_new, "CHANGES_DIR", tmp_path / "changes")
    with pytest.raises(SystemExit) as exc:
        changes_new.main(["--kind", "fix", "--title", "A past bug", "--problem"])
    assert exc.value.code == 2
    assert list(tmp_path.iterdir()) == []


def test_collation_ignores_legacy_problem_fragments(tmp_path, monkeypatch):
    changes = tmp_path / ".changes" / "unreleased"
    changes.mkdir(parents=True)
    old = tmp_path / "knowledge" / "problems" / "20260920T000000-old.md"
    old.parent.mkdir(parents=True)
    old.write_text(render_fragment(kind="fix", scope="test", pr="", title="Old problem", body="- Cause: history"), encoding="utf-8")
    ledger = tmp_path / "CHANGELOG.md"
    original = "# Change log\n\n" + ENTRIES_MARKER + "\n"
    ledger.write_text(original, encoding="utf-8")
    monkeypatch.setattr(changes_collate, "CHANGES_DIR", changes)
    monkeypatch.setattr(changes_collate, "CHANGELOG", ledger)
    monkeypatch.setattr(changes_collate, "read_watermark", lambda: None)
    assert changes_collate.main(["--date", "2026-09-20", "--fragments-only"]) == 0
    assert ledger.read_text(encoding="utf-8") == original
    assert old.exists()  # inactive history is not consumed or modified
    assert not (tmp_path / "PROBLEM_LOG.md").exists()


def test_active_agent_prompts_no_longer_require_problem_footer():
    root = Path(__file__).resolve().parents[1]
    for path in (root / ".cursor" / "agents").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "problem_log=" not in text, path
        assert "PROBLEM_LOG" not in text, path
    assert not (root / ".cursor/rules/problem-log.mdc").exists()
    assert not (root / "PROBLEM_LOG.md").exists()
    assert not (root / "BACKLOG.md").exists()
