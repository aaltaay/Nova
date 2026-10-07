"""The always-on context budget (ADR 051): one byte total for everything that
loads on every agent request, not a line cap on one file.

Every new chat pays for ``AGENTS.md``, ``CLAUDE.md`` and every rule under
``.cursor/rules/`` marked ``alwaysApply: true`` before the first question is
asked. On 2026-10-07 that set was 170,606 bytes, and only ``AGENTS.md`` was
measured (``file_size_hard``, 700 lines): the rules weighed twice the
constitution and nothing watched them. The policy now:

* the set's total may not pass ``ALWAYS_ON_BUDGET_BYTES`` (``always_on_budget``,
  gate); a change that needs more room moves text behind ``globs`` or into a
  pointer. The budget only ratchets down: when the total sits 5,000 bytes or
  more under it, the next change to the set lowers it;
* a change that grows the total is reported (``always_on_growth``, advisory)
  so the PR body can say why;
* ``session_brief_line`` prints the total every chat, so the number is seen.

A rule earns ``alwaysApply`` only when an agent editing *any* file -- a README
typo included -- could lose money or break delivery without it. Everything
else gets ``globs`` or stays agent-requested. One law has one home; the other
files hold a line and a link. A rule a script enforces shrinks to a pointer.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# 139,179 bytes on 2026-10-07 after ADR 051's first cut (from 170,606). The
# budget only ratchets down: when the total sits 5,000+ under it, lower it.
ALWAYS_ON_BUDGET_BYTES = 145_000
ALWAYS_ON_FILES = ("AGENTS.md", "CLAUDE.md")
RULES_DIR = ".cursor/rules"

_ALWAYS_APPLY_RE = re.compile(r"^alwaysApply:\s*true\s*$", re.MULTILINE)
_FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.DOTALL)


def is_always_on_rule(text: str) -> bool:
    """``alwaysApply: true`` inside the rule's front matter."""
    m = _FRONT_MATTER_RE.match(text)
    return bool(m and _ALWAYS_APPLY_RE.search(m.group(1)))


def _size(raw: bytes) -> int:
    """Bytes as git stores them: CRLF counts as one, so a Windows checkout and
    the blob at ``--base`` measure the same text the same."""
    return len(raw.replace(b"\r\n", b"\n"))


def always_on_set(repo_root: Path) -> dict[str, int]:
    """``{relative path: bytes}`` for everything injected on every request."""
    out: dict[str, int] = {}
    for rel in ALWAYS_ON_FILES:
        p = repo_root / rel
        if p.is_file():
            out[rel] = _size(p.read_bytes())
    rules = repo_root / RULES_DIR
    if rules.is_dir():
        for p in sorted(rules.glob("*.mdc")):
            try:
                raw = p.read_bytes()
            except OSError:
                continue
            if is_always_on_rule(raw.decode("utf-8", errors="replace")):
                out[f"{RULES_DIR}/{p.name}"] = _size(raw)
    return out


def always_on_total_at(repo_root: Path, sha: str) -> int | None:
    """The set's total at ``sha``; None when git cannot answer."""
    try:
        listing = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", sha, "--", *ALWAYS_ON_FILES, RULES_DIR],
            cwd=repo_root, capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    if listing.returncode != 0:
        return None
    total = 0
    for rel in listing.stdout.split():
        if not (rel in ALWAYS_ON_FILES or rel.endswith(".mdc")):
            continue
        try:
            blob = subprocess.run(
                ["git", "show", f"{sha}:{rel}"], cwd=repo_root, capture_output=True, check=False,
            )
        except OSError:
            return None
        if blob.returncode != 0:
            continue
        if rel in ALWAYS_ON_FILES or is_always_on_rule(blob.stdout.decode("utf-8", errors="replace")):
            total += _size(blob.stdout)
    return total


def check_always_on(repo_root: Path, finding_cls: type, base: str | None = None,
                    budget: int = ALWAYS_ON_BUDGET_BYTES) -> list:
    """``always_on_budget`` past the budget; ``always_on_growth`` when the total grew."""
    members = always_on_set(repo_root)
    total = sum(members.values())
    findings = []
    if total > budget:
        largest = sorted(members.items(), key=lambda kv: -kv[1])[:3]
        who = ", ".join(f"{rel} {size:,}" for rel, size in largest)
        findings.append(finding_cls(
            kind="always_on_budget", path=RULES_DIR,
            detail=(f"{total:,} bytes load on every request > budget {budget:,} (ADR 051); "
                    f"largest: {who} -- move text behind globs or into a pointer"),
        ))
    if base:
        before = always_on_total_at(repo_root, base)
        if before is not None and total > before:
            findings.append(finding_cls(
                kind="always_on_growth", path=RULES_DIR,
                detail=(f"always-on context grew {before:,} -> {total:,} bytes (+{total - before:,}); "
                        "the PR body says why, or the text moves behind globs (ADR 051)"),
            ))
    return findings


def report_fields(repo_root: Path) -> dict:
    """The JSON report's two keys for this check."""
    return {"always_on_bytes": always_on_set(repo_root), "always_on_budget": ALWAYS_ON_BUDGET_BYTES}


def report_lines(report: dict) -> list[str]:
    """The human report's block, largest first."""
    members = report.get("always_on_bytes") or {}
    if not members:
        return []
    total = sum(members.values())
    lines = [f"Always-on context: {total:,} bytes of {report.get('always_on_budget', 0):,} budget (ADR 051):"]
    lines += [f"  {size:7,d}  {path}" for path, size in sorted(members.items(), key=lambda kv: (-kv[1], kv[0]))]
    return lines


def session_brief_line(repo_root: Path, budget: int = ALWAYS_ON_BUDGET_BYTES) -> str:
    members = always_on_set(repo_root)
    total = sum(members.values())
    rules = sum(1 for rel in members if rel.endswith(".mdc"))
    return (f"Always-on context: {total:,} bytes of {budget:,} budget "
            f"(AGENTS.md + CLAUDE.md + {rules} always-on rules; ADR 051; "
            "`py -3 tools/maintainer_checks.py`)")
