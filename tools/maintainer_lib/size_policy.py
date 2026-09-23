"""File-size policy: a soft limit that asks for a reason, a ceiling that blocks.

AGENTS.md §2.3. A line count is a proxy for "an agent can read this file in one
pass and see one concern". The old rule was a cliff -- fine at 399, broken at
401 -- and the tree bunched just under it (on 2026-09-23 ten Python / TS files
sat at 395-400 lines, against seven in the fifteen lines below), because
squeezing a file was cheaper than splitting it. The policy now:

* a code file over ``SOFT_LIMIT`` needs a reason: it is split, or its header
  says why it is one concern (``maintainer: one-concern <reason>``);
* a file over the soft limit without that reason may not grow (``--base``);
* nothing passes ``CEILING``, reason or not.

Constants tables are data, not logic: they skip the soft limit and keep the
ceiling. Tests are exempt. Entry points keep their own logical-line limits.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

from maintainer_lib.sizes import LOGICAL_LIMIT_FILES, count_logical_lines

SOFT_LIMIT = 400
CEILING = 800
DOMAIN_CSS_LIMIT = 1000  # stylesheets: advisory only, prefer <= 700

CODE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".jsx"})

# Tables of tunables (AGENTS.md §6.1) -- long by nature, one concern each.
DATA_PREFIXES = ("backend/constants_", "frontend/src/constantGroups/")
DATA_FILES = frozenset({"backend/constants.py", "frontend/src/constants.ts"})

# The reason must be on the marker's own line and read as a sentence.
ONE_CONCERN_RE = re.compile(r"maintainer:\s*one-concern\b[ \t:\-–—]*(?P<reason>[^\n]*)")
ONE_CONCERN_MIN_REASON = 20
ONE_CONCERN_HEADER_LINES = 40

_COMMENT_CLOSERS = ('"""', "'''", "*/", "-->")


def count_lines(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def is_data_file(rel: str) -> bool:
    return rel in DATA_FILES or rel.startswith(DATA_PREFIXES)


def one_concern_reason(path: Path) -> str | None:
    """The header's one-concern reason: None without a marker, "" when blank."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            head = [next(handle, "") for _ in range(ONE_CONCERN_HEADER_LINES)]
    except OSError:
        return None
    match = ONE_CONCERN_RE.search("".join(head))
    if match is None:
        return None
    reason = match.group("reason").strip()
    for closer in _COMMENT_CLOSERS:
        if reason.endswith(closer):
            reason = reason[: -len(closer)].rstrip()
    return reason


def resolve_base(repo_root: Path, base: str | None) -> str | None:
    """The merge-base of ``base`` and HEAD, or None when there is nothing to compare.

    A PR checkout is the merge commit, so its merge-base with the target branch
    is the target's tip: the comparison is exactly this change.
    """
    if not base:
        return None
    try:
        out = subprocess.run(
            ["git", "merge-base", base, "HEAD"],
            cwd=repo_root, capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and sha else None


def lines_at(repo_root: Path, sha: str, rel: str) -> int | None:
    """Raw line count of ``rel`` at ``sha``; None when the file did not exist."""
    try:
        out = subprocess.run(
            ["git", "show", f"{sha}:{rel}"],
            cwd=repo_root, capture_output=True, check=False,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    text = out.stdout.decode("utf-8", errors="replace")
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def check_file_sizes(
    files: list[Path],
    rel_fn: Callable[[Path], str],
    finding_cls: type,
    hard_limits: dict[str, int],
    skip_fn: Callable[[Path], bool],
    base_lines: Callable[[str], int | None] | None = None,
) -> list:
    """Size findings. ``base_lines`` (rel -> lines at the base, None = new file)
    turns on the growth check; without it growth is not judged."""
    findings = []
    for path in files:
        rel = rel_fn(path)
        if rel not in hard_limits and skip_fn(path):
            continue
        lines = count_lines(path)

        if rel in hard_limits:
            limit = hard_limits[rel]
            logical = rel in LOGICAL_LIMIT_FILES
            counted = count_logical_lines(path) if logical else lines
            if counted > limit:
                detail = (
                    f"{counted} logical lines > entry-point limit {limit} ({lines} raw)"
                    if logical
                    else f"{counted} lines > hard limit {limit}"
                )
                findings.append(finding_cls(kind="file_size_hard", path=rel, detail=detail))
            continue

        if path.suffix == ".css":
            if lines > DOMAIN_CSS_LIMIT:
                findings.append(finding_cls(
                    kind="file_size", path=rel,
                    detail=f"{lines} lines > CSS stylesheet limit {DOMAIN_CSS_LIMIT}",
                ))
            continue
        if path.suffix not in CODE_SUFFIXES:
            continue

        if lines > CEILING:
            findings.append(finding_cls(
                kind="file_size_ceiling", path=rel,
                detail=f"{lines} lines > ceiling {CEILING} -- split it; no reason covers this",
            ))
            continue
        if lines <= SOFT_LIMIT or is_data_file(rel):
            continue

        reason = one_concern_reason(path)
        if reason is not None and len(reason) >= ONE_CONCERN_MIN_REASON:
            continue
        if reason is not None:
            findings.append(finding_cls(
                kind="one_concern_no_reason", path=rel,
                detail=(f"`maintainer: one-concern` needs a reason of at least "
                        f"{ONE_CONCERN_MIN_REASON} characters on its own line"),
            ))
            continue
        findings.append(finding_cls(
            kind="file_size", path=rel,
            detail=(f"{lines} lines > soft limit {SOFT_LIMIT} -- split it, or say why it "
                    "is one concern (`maintainer: one-concern <reason>` in the header)"),
        ))
        if base_lines is None:
            continue
        before = base_lines(rel)
        if before is None or before < lines:
            was = "new file" if before is None else f"{before} -> {lines} lines"
            findings.append(finding_cls(
                kind="file_size_growth", path=rel,
                detail=(f"grew past the soft limit {SOFT_LIMIT} ({was}) without a "
                        "one-concern reason -- split it or state the reason"),
            ))
    return findings
