"""The authored work-package plan, and what it says to do next.

`knowledge/backlog-packages.json` is AUTHORED -- rank, objective, definition
of done, and which issues batch into which pull request. GitHub milestones are
its projection. Issue *state* (open/closed, labels) always comes from GitHub,
so a stale file degrades a listing but cannot resurrect closed work.

Selection is BATCH-driven, not package-driven: a package is startable when it
has an ungated, unclaimed batch with open issues left. Package `readiness` is
a human-facing summary, so ready work inside an otherwise-blocked package
stays reachable."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from tools.backlog_github import (
    INBOX_TITLE,
    KINDS,
    NO_MILESTONE,
    SEVERITIES,
    URGENT,
    domain_labels,
    label_names,
    milestone_title,
    repo_slug,
    severity_of,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_PATH = REPO_ROOT / "knowledge" / "backlog-packages.json"

READY = "ready-now"


def load_packages(path: Path | None = None) -> list[dict[str, Any]]:
    """Packages in working order. Rank is authored; ties fall back to slug."""
    target = path or PACKAGES_PATH
    data = json.loads(target.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise RuntimeError(f"{target}: unsupported schema_version {data.get('schema_version')!r}")
    return sorted(data.get("packages", []), key=lambda p: (p.get("rank", 999), p.get("slug", "")))


def milestone_description(pkg: dict[str, Any]) -> str:
    """What a non-Claude consumer sees on the milestone itself.

    Kept self-contained: objective, gate, and the acceptance criteria. GitHub
    truncates nothing at this length and it saves a reader one hop.
    """
    parts = [pkg["objective"]]
    if pkg.get("gate"):
        parts.append(f"GATE: {pkg['gate']}")
    parts.append("Done when: " + " | ".join(pkg.get("done", [])))
    parts.append(f"Plan: BACKLOG.md ({pkg['slug']}) - run `py -3 tools/backlog_triage.py next`")
    return "\n\n".join(parts)


# --------------------------------------------------------------------------

def hygiene_gaps(issue: dict[str, Any]) -> list[str]:
    """Why this issue is not yet routable by an agent picking up work.

    ``no-package`` is reported first because it is the gap that hides an
    issue from every package-shaped consumer.
    """
    names = label_names(issue)
    gaps: list[str] = []
    if milestone_title(issue) == NO_MILESTONE:
        gaps.append("no-package")
    if not names & set(SEVERITIES):
        gaps.append("no-priority")
    if not names & set(KINDS):
        gaps.append("no-kind")
    if not any(n.startswith("domain:") for n in names):
        gaps.append("no-domain")
    if "deferred" not in names:
        # Without it the issue is absent from deferred_log.py status, which
        # is what agents are told to consult before any fix.
        gaps.append("no-deferred")
    return gaps


def duplicate_aliases(issues: Iterable[dict[str, Any]]) -> dict[str, list[int]]:
    """Legacy ``D-NNN`` prefixes the retired next-id allocator raced on.

    GitHub ``#NNN`` is the durable id (AGENTS.md 7.2c). These survive only in
    titles and history; report them so nobody cites an ambiguous alias.
    """
    seen: dict[str, list[int]] = {}
    for issue in issues:
        match = re.match(r"\s*(D-\d+)\b", issue.get("title") or "")
        if match:
            seen.setdefault(match.group(1), []).append(int(issue["number"]))
    return {alias: sorted(nums) for alias, nums in seen.items() if len(nums) > 1}


def rollup(issues: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-package counts plus the issue numbers, for rendering and checks."""
    out: dict[str, dict[str, Any]] = {}
    for issue in issues:
        pkg = milestone_title(issue)
        bucket = out.setdefault(
            pkg,
            {"open": 0, "numbers": [], **{sev: 0 for sev in SEVERITIES}, "unprioritised": 0},
        )
        bucket["open"] += 1
        bucket["numbers"].append(int(issue["number"]))
        sev = severity_of(issue)
        if sev:
            bucket[sev] += 1
        else:
            bucket["unprioritised"] += 1
    for bucket in out.values():
        bucket["numbers"].sort()
    return out


def plan_drift(packages: list[dict[str, Any]], issues: list[dict[str, Any]]) -> list[str]:
    """Where the authored plan and GitHub disagree.

    Only open issues are compared: an issue the plan lists that has since
    closed is completed work, not drift.
    """
    open_by_number = {int(i["number"]): i for i in issues}
    problems: list[str] = []
    planned: dict[int, str] = {}
    for pkg in packages:
        for number in pkg["issues"]:
            if number in planned:
                problems.append(f"#{number} is in two packages: {planned[number]} and {pkg['slug']}")
            planned[number] = pkg["slug"]

    for number, issue in sorted(open_by_number.items()):
        if number not in planned:
            if milestone_title(issue) == INBOX_TITLE:
                continue  # queued for routing, not drift
            problems.append(f"#{number} is open but in no package (add it to backlog-packages.json)")
            continue
        want = next(p["title"] for p in packages if p["slug"] == planned[number])
        have = milestone_title(issue)
        if have != want:
            problems.append(f"#{number} milestone is {have!r}, plan says {want!r} (run sync)")
    return problems


def analyse(
    issues: list[dict[str, Any]],
    milestones: list[dict[str, Any]],
    packages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # Sort here rather than trusting the caller: analyse() is also reached
    # from tests and from a hand-built list, and a mis-ordered rollup reads
    # as a re-prioritised backlog.
    packages = sorted(packages or [], key=lambda p: (p.get("rank", 999), p.get("slug", "")))
    gaps = {int(i["number"]): hygiene_gaps(i) for i in issues if hygiene_gaps(i)}
    counts = rollup(issues)
    order = [p["title"] for p in packages] or sorted(
        ms.get("title", "") for ms in milestones if ms.get("state") == "open"
    )
    return {
        "repo": repo_slug(),
        "open_issues": len(issues),
        "packages": counts,
        "package_order": order,
        "empty_packages": [t for t in order if t not in counts and t != INBOX_TITLE],
        "hygiene_gaps": gaps,
        "duplicate_aliases": duplicate_aliases(issues),
        "unpackaged": sorted(
            int(i["number"]) for i in issues if milestone_title(i) == NO_MILESTONE
        ),
        "drift": plan_drift(packages, issues) if packages else [],
        "inbox": sorted(int(i["number"]) for i in issues if milestone_title(i) == INBOX_TITLE),
        "inbox_urgent": sorted(
            int(i["number"]) for i in issues
            if milestone_title(i) == INBOX_TITLE and severity_of(i) in URGENT
        ),
    }



def candidate_packages(
    issue: dict[str, Any],
    packages: list[dict[str, Any]],
    by_number: dict[int, dict[str, Any]],
) -> list[tuple[str, int]]:
    """Packages already holding issues that share this one's domain labels.

    A *suggestion*, never an assignment: domain overlap says "these touch
    similar code", which is a weaker claim than "these serve the same
    outcome". The routing decision stays with whoever runs triage.
    """
    mine = domain_labels(issue)
    if not mine:
        return []
    scored: list[tuple[str, int]] = []
    for pkg in packages:
        if pkg["title"] == INBOX_TITLE:
            continue
        hits = sum(
            1 for n in pkg["issues"]
            if n in by_number and domain_labels(by_number[n]) & mine
        )
        if hits:
            scored.append((pkg["slug"], hits))
    return sorted(scored, key=lambda s: (-s[1], s[0]))[:3]



def with_inbox(
    packages: list[dict[str, Any]], issues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Fill the inbox package's issue list from GitHub.

    The authored JSON cannot list issues that did not exist when it was
    written, so inbox membership is read from the milestone instead. Without
    this the inbox always looks empty and `next` would never mention it.
    """
    queued = sorted(int(i["number"]) for i in issues if milestone_title(i) == INBOX_TITLE)
    return [dict(p, issues=queued) if p["title"] == INBOX_TITLE else p for p in packages]


def pick_next(
    packages: list[dict[str, Any]],
    open_numbers: set[int],
    claimed: Iterable[int] = (),
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The highest-ranked package an agent can actually start, plus what it skipped.

    Selection is BATCH-driven, not package-driven. A package is startable when
    it holds an ungated, unclaimed batch with open issues -- so ready work does
    not get stranded inside a package whose overall `readiness` is blocked by
    some *other* batch, and a `ready-now` package whose remaining batches are
    all gated no longer stops the walk.

    Skipped packages are returned alongside with a stated reason rather than
    hidden, so a decision or a claim is surfaced instead of silently costing
    the reader a package.
    """
    held = set(claimed)
    skipped: list[dict[str, Any]] = []
    for pkg in packages:
        remaining = set(pkg["issues"]) & open_numbers
        if not remaining:
            continue
        startable = next_pr(pkg, open_numbers, held)
        if startable is not None:
            return pkg, skipped
        # No startable batch. Say WHICH of the two reasons it is -- "gated"
        # and "someone else holds it" call for different responses from the
        # reader, and a wrong reason is worse than none.
        blocked_by_claim = any(
            set(pr["issues"]) & held
            for pr in pkg.get("prs", [])
            if not pr.get("gated") and set(pr["issues"]) & open_numbers
        )
        reason = (
            "every startable batch is already claimed" if blocked_by_claim
            else "every remaining batch is gated on a decision"
        )
        skipped.append(dict(pkg, _skip_reason=reason))
    return None, skipped


def next_pr(
    pkg: dict[str, Any], open_numbers: set[int], claimed: Iterable[int] = ()
) -> dict[str, Any] | None:
    """The first ungated, unclaimed PR batch with open issues left.

    A batch is unavailable if ANY of its issues is under a live claim -- the
    batch is one PR, so a partially-claimed batch is not startable.
    """
    held = set(claimed)
    for pr in pkg.get("prs", []):
        if pr.get("gated"):
            continue
        if set(pr["issues"]) & held:
            continue
        if set(pr["issues"]) & open_numbers:
            return pr
    return None


