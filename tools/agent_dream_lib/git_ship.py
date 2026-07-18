"""Optional commit/push after a dream --write pass."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitResult:
    committed: bool
    pushed: bool
    sha: str | None
    message: str
    detail: str


def _run(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def ship_dream_changes(
    repo_root: Path,
    files: list[str],
    *,
    commit: bool,
    push: bool,
    message: str | None = None,
) -> GitResult:
    if not commit:
        return GitResult(False, False, None, "", "commit not requested")

    # Stage dream-touched paths plus the dream subsystem itself
    to_add = [f for f in files if (repo_root / f).exists()]
    for extra in (
        "tools/agent_dream.py",
        "tools/agent_dream_lib",
        "tools/test_agent_dream.py",
        ".cursor/agent-system/DREAMS.md",
        ".cursor/agent-system/openclaw-MEMORY.md",
        "knowledge/obsidian/00-System/Agent-Dreaming.md",
        "knowledge/obsidian/00-System/Memory-Router.md",
        "knowledge/obsidian/00-System/Agent-Fleet-Map.md",
        "knowledge/obsidian/03-Nova-Decisions/_Agent-Dream-Hygiene.md",
        "knowledge/task-log/2026-07-18-agent-dreaming.md",
        "knowledge/task-log/INDEX.md",
        "docs/agent-operations.md",
        "CHANGELOG.md",
        ".claude/settings.json",
        ".cursor/agents/docs.md",
        ".cursor/agent-system/registry.json",
        ".cursor/rules/specialist-routing.mdc",
    ):
        p = repo_root / extra
        if p.exists() and extra not in to_add:
            to_add.append(extra)

    if not to_add:
        return GitResult(False, False, None, "", "nothing to stage")

    add = _run(repo_root, ["add", "--", *to_add])
    if add.returncode != 0:
        return GitResult(False, False, None, "", f"git add failed: {add.stderr.strip()}")

    status = _run(repo_root, ["status", "--porcelain"])
    if not status.stdout.strip():
        return GitResult(False, False, None, "", "working tree clean after add")

    msg = message or (
        "Consolidate agent memory via Nova dream pass "
        "(light/REM/deep + bridges)."
    )
    commit_proc = _run(repo_root, ["commit", "-m", msg])
    if commit_proc.returncode != 0:
        return GitResult(
            False,
            False,
            None,
            msg,
            f"git commit failed: {(commit_proc.stderr or commit_proc.stdout).strip()}",
        )

    sha_proc = _run(repo_root, ["rev-parse", "--short", "HEAD"])
    sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else None
    pushed = False
    detail = "committed"
    if push:
        push_proc = _run(repo_root, ["push"])
        if push_proc.returncode != 0:
            detail = f"committed but push failed: {push_proc.stderr.strip()}"
        else:
            pushed = True
            detail = "committed and pushed"
    return GitResult(True, pushed, sha, msg, detail)
