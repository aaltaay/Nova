"""Local/generated artifact path checks for the maintainer scanner."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

ARTIFACT_PATHS = (
    "frontend/dist",
    "backend/.cache",
    ".env",
)


def git_tracked_paths(repo_root: Path, paths: tuple[str, ...] = ARTIFACT_PATHS) -> set[str]:
    """Return repo-relative paths currently tracked by git (empty if unavailable)."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", *paths],
            cwd=repo_root,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if out.returncode != 0:
        return set()
    raw = out.stdout.decode("utf-8", errors="replace")
    return {p.replace("\\", "/") for p in raw.split("\0") if p}


def check_artifacts(
    repo_root: Path,
    finding_cls: type,
    paths: tuple[str, ...] = ARTIFACT_PATHS,
    tracked_fn: Callable[[], set[str]] | None = None,
) -> list:
    """Informational if gitignored; non-baseline if tracked."""
    findings = []
    tracked = tracked_fn() if tracked_fn is not None else git_tracked_paths(repo_root, paths)
    for rel in paths:
        path = repo_root / rel
        if not path.exists():
            continue
        if rel in tracked or any(
            t == rel or t.startswith(rel.rstrip("/") + "/") for t in tracked
        ):
            findings.append(
                finding_cls(
                    kind="artifact_tracked",
                    path=rel,
                    detail="generated/local path is tracked by git — untrack or gitignore",
                    baseline=False,
                )
            )
        else:
            findings.append(
                finding_cls(
                    kind="artifact_present",
                    path=rel,
                    detail="local/generated path exists (gitignored; informational)",
                    baseline=True,
                )
            )
    return findings
