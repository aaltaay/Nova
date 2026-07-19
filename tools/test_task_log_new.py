"""Tests for tools/task_log_new.py"""
from __future__ import annotations

from pathlib import Path

from tools.task_log_new import main


def test_scaffold_and_index(tmp_path: Path, monkeypatch):
    log_dir = tmp_path / "knowledge" / "task-log"
    log_dir.mkdir(parents=True)
    (log_dir / "_template.md").write_text(
        "# YYYY-MM-DD — Short title\n\n## Why this approach\n\n",
        encoding="utf-8",
    )
    (log_dir / "INDEX.md").write_text(
        "# Task log index\n\n"
        "| Date | Entry | One-line summary |\n"
        "|------|-------|------------------|\n"
        "| 2026-01-01 | [Old](2026-01-01-old.md) | prior |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("tools.task_log_new.REPO_ROOT", tmp_path)
    monkeypatch.setattr("tools.task_log_new.LOG_DIR", log_dir)
    monkeypatch.setattr("tools.task_log_new.INDEX_PATH", log_dir / "INDEX.md")
    monkeypatch.setattr("tools.task_log_new.TEMPLATE_PATH", log_dir / "_template.md")

    assert main(["--slug", "Demo Fix!", "--title", "Demo fix", "--date", "2026-07-18"]) == 0
    path = log_dir / "2026-07-18-demo-fix.md"
    assert path.is_file()
    assert "Demo fix" in path.read_text(encoding="utf-8")
    index = (log_dir / "INDEX.md").read_text(encoding="utf-8")
    assert "2026-07-18-demo-fix.md" in index
    # newest row immediately under header separator
    sep = index.index("|------")
    assert "2026-07-18" in index[sep : sep + 200]
    assert index.index("2026-07-18") < index.index("2026-01-01")


def test_dry_run_no_write(tmp_path: Path, monkeypatch):
    log_dir = tmp_path / "knowledge" / "task-log"
    log_dir.mkdir(parents=True)
    monkeypatch.setattr("tools.task_log_new.REPO_ROOT", tmp_path)
    monkeypatch.setattr("tools.task_log_new.LOG_DIR", log_dir)
    monkeypatch.setattr("tools.task_log_new.INDEX_PATH", log_dir / "INDEX.md")
    monkeypatch.setattr("tools.task_log_new.TEMPLATE_PATH", log_dir / "_template.md")
    assert main(["--slug", "x", "--title", "X", "--dry-run"]) == 0
    assert list(log_dir.glob("*.md")) == []
