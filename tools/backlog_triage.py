#!/usr/bin/env python3
"""Nova backlog triage: what to work on next, and whether the board still says so.

The backlog is organised into **work packages**. A package is a coherent
outcome, not a module: "after this, recording cannot wedge the desk" rather
than "backend/capture". Every open issue belongs to exactly one.

Two homes, one direction of flow:

  ``knowledge/backlog-packages.json``  AUTHORED. Rank, objective, definition
      of done, and which issues batch into which pull request.
  **GitHub milestones**                PROJECTED from that file by ``sync``.
      First-class in the REST/GraphQL API and in issue search
      (``milestone:"01 - ..."``), so a bot that is not Claude Code -- an
      Action, a dashboard, a webhook, ``gh`` in a shell -- reads the plan
      without parsing Markdown.

Issue *state* (open/closed, labels) always comes from GitHub and never from
the JSON, so a stale file degrades a listing but cannot resurrect closed work.
``check`` reports drift between the two; nothing here self-heals.

The agent entry point is ``next``: it prints one package, one pull request,
and the acceptance criteria, so a fresh session can start without reading
the whole backlog.

Usage:
  python3 tools/backlog_triage.py next              # <- "what do I work on?"
  python3 tools/backlog_triage.py triage            # <- route the inbox
  python3 tools/backlog_triage.py claims            # <- who holds what
  python3 tools/backlog_triage.py claim --package recorder-safety
  python3 tools/backlog_triage.py release --package recorder-safety
  python3 tools/backlog_triage.py next --json
  python3 tools/backlog_triage.py report            # package rollup + gaps
  python3 tools/backlog_triage.py report --json
  python3 tools/backlog_triage.py check             # exit 1 on gaps or drift
  python3 tools/backlog_triage.py sync              # packages -> milestones
  python3 tools/backlog_triage.py sync --dry-run
  python3 tools/backlog_triage.py sync-map --issue NNN
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

DEFAULT_REPO = "aaltaay/Nova"
REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_PATH = REPO_ROOT / "knowledge" / "backlog-packages.json"

EXIT_OK = 0
EXIT_GAPS = 1
EXIT_ERROR = 2

SEVERITIES = ("P0", "P1", "P2", "P3")
KINDS = ("bug", "enhancement", "decision", "documentation")

# A package with no milestone is invisible to every GitHub-side consumer,
# so "unassigned" is a gap, not a state.
NO_MILESTONE = "(no package)"

MAP_BEGIN = "<!-- backlog-map:begin -->"
MAP_END = "<!-- backlog-map:end -->"

READY = "ready-now"

# The Backlog Map issue is a rendered view of the backlog, not an item in it.
# Without this it would report itself as an untriaged issue forever.
META_LABEL = "backlog-map"

# The inbox. A new issue is assigned here by .github/workflows/backlog-inbox.yml
# the moment it is opened, so it is visible to `next` within minutes instead of
# waiting for the Monday sweep. Routing it onward is a judgement call -- which
# outcome does this issue serve? -- so nothing guesses it from a label. Issues
# leave the inbox by being added to a package in knowledge/backlog-packages.json,
# never by being worked on from here.
INBOX_TITLE = "00 - Untriaged"

# An untriaged P0/P1 is the failure this inbox exists to prevent: `next` would
# hand out routine work while a desk-breaking bug sat unrouted. `check` fails
# on those rather than treating the inbox as uniformly fine.
URGENT = ("P0", "P1")

# --- claims ---------------------------------------------------------------
#
# Agents run from several tools (Claude Code, Codex, Cursor) and all of them
# authenticate as the same GitHub account, so `assignee` cannot say WHO holds
# a piece of work. GitHub is the only substrate every tool can see, so the
# claim lives there: a `claimed` label for cheap filtering plus a structured
# comment carrying agent id, branch and timestamp.
#
# The lock unit is the PR BATCH, not the issue -- the batch is already the
# unit of work, so locking per-issue would create four locks for one job.
#
# This is ADVISORY. Two agents can both read "unclaimed" before either writes;
# GitHub offers no compare-and-swap on labels. `claim` therefore re-reads
# after writing and yields if an earlier live claim exists (earliest `at`
# wins), which makes a collision detectable and resolvable rather than
# impossible. An agent that ignores the protocol will still collide.
CLAIM_LABEL = "claimed"

# Long enough for a real session on a multi-issue batch, short enough that a
# crashed agent does not block a package for a working day.
CLAIM_TTL_HOURS = 4

CLAIM_BEGIN = "<!-- nova-claim"
CLAIM_RELEASE = "<!-- nova-claim-release"
CLAIM_END = "-->"

Runner = Callable[..., subprocess.CompletedProcess[str]]


# --------------------------------------------------------------------------
# gh plumbing
# --------------------------------------------------------------------------


def repo_slug() -> str:
    return os.environ.get("NOVA_GITHUB_REPO", DEFAULT_REPO)


def run_gh(args: list[str], *, runner: Runner = subprocess.run) -> subprocess.CompletedProcess[str]:
    return runner(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )


def is_meta(issue: dict[str, Any]) -> bool:
    return META_LABEL in label_names(issue)


def fetch_issues(*, runner: Runner = subprocess.run) -> list[dict[str, Any]]:
    """Open backlog issues. Meta issues (the Map itself) are excluded.

    Raises on a gh failure rather than returning an empty list: an empty
    backlog and an unreadable one must not look the same.
    """
    proc = run_gh(
        [
            "issue", "list", "--repo", repo_slug(), "--state", "open", "--limit", "500",
            "--json", "number,title,labels,milestone,url,createdAt,updatedAt",
        ],
        runner=runner,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh issue list failed: {proc.stderr.strip()}")
    return [i for i in json.loads(proc.stdout or "[]") if not is_meta(i)]


def fetch_milestones(*, runner: Runner = subprocess.run) -> list[dict[str, Any]]:
    proc = run_gh(["api", f"repos/{repo_slug()}/milestones?state=all&per_page=100"], runner=runner)
    if proc.returncode != 0:
        raise RuntimeError(f"gh api milestones failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout or "[]")


# --------------------------------------------------------------------------
# authored packages
# --------------------------------------------------------------------------


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
# pure analysis
# --------------------------------------------------------------------------


def label_names(issue: dict[str, Any]) -> set[str]:
    return {lbl.get("name", "") for lbl in issue.get("labels") or []}


def milestone_title(issue: dict[str, Any]) -> str:
    ms = issue.get("milestone")
    if not ms:
        return NO_MILESTONE
    return ms.get("title") or NO_MILESTONE


def severity_of(issue: dict[str, Any]) -> str:
    names = label_names(issue)
    for sev in SEVERITIES:
        if sev in names:
            return sev
    return ""


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


def domain_labels(issue: dict[str, Any]) -> set[str]:
    return {n for n in label_names(issue) if n.startswith("domain:")}


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


def render_triage(
    inbox: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    by_number: dict[int, dict[str, Any]],
) -> str:
    if not inbox:
        return "Inbox empty -- every open issue is routed to a package."
    lines = [
        f"{len(inbox)} issue(s) awaiting routing.",
        "",
        "For each: decide which package's OUTCOME it serves, add its number to that",
        "package's `issues` (and to a PR batch) in knowledge/backlog-packages.json,",
        "then run `py -3 tools/backlog_triage.py sync`.",
        "",
    ]
    for issue in sorted(inbox, key=lambda i: (severity_of(i) or "P9", int(i["number"]))):
        number = int(issue["number"])
        sev = severity_of(issue) or "unprioritised"
        doms = ", ".join(sorted(domain_labels(issue))) or "no domain label"
        lines.append(f"  #{number}  [{sev}] {issue.get('title', '')[:66]}")
        lines.append(f"      {doms}")
        hints = candidate_packages(issue, packages, by_number)
        if hints:
            lines.append(
                "      shares a domain with: "
                + ", ".join(f"{slug} ({n})" for slug, n in hints)
                + "   <- suggestion only"
            )
        if sev in URGENT:
            lines.append("      URGENT -- check fails while this sits here")
        lines.append("")
    return "\n".join(lines).rstrip()


# --------------------------------------------------------------------------
# claims -- who is already holding this work
# --------------------------------------------------------------------------


def agent_id() -> str:
    """Self-reported. Cooperative, not adversarial -- nobody is defending
    against a hostile agent, only stopping honest ones duplicating work."""
    return os.environ.get("NOVA_AGENT_ID") or "unknown-agent"


def batch_ref(slug: str, index: int) -> str:
    return f"{slug}#{index}"


def format_claim(*, agent: str, batch: str, branch: str, at: datetime) -> str:
    return (
        f"{CLAIM_BEGIN}\n"
        f"agent: {agent}\n"
        f"batch: {batch}\n"
        f"branch: {branch}\n"
        f"at: {at.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"{CLAIM_END}\n"
        f"Claimed by `{agent}` on branch `{branch}` for batch `{batch}`. "
        f"Stale after {CLAIM_TTL_HOURS}h with no branch activity -- "
        f"`py -3 tools/backlog_triage.py claims` lists holders."
    )


def format_release(*, agent: str, batch: str) -> str:
    return (
        f"{CLAIM_RELEASE} {CLAIM_END}\n"
        f"Released by `{agent}` (batch `{batch}`)."
    )


def parse_claim(body: str) -> dict[str, str] | None:
    """Pull the structured block out of a claim comment. None if absent."""
    if CLAIM_BEGIN not in body:
        return None
    block = body.split(CLAIM_BEGIN, 1)[1].split(CLAIM_END, 1)[0]
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields or None


def _as_dt(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def active_claim(
    comments: list[dict[str, Any]], *, now: datetime, ttl_hours: int = CLAIM_TTL_HOURS
) -> dict[str, Any] | None:
    """The claim in force on an issue, or None.

    The newest marker wins: a release after a claim clears it. A claim older
    than the TTL is reported with ``stale: True`` rather than hidden, so a
    caller can decide between reclaiming and reporting.
    """
    markers: list[tuple[str, str, dict[str, str] | None]] = []
    for comment in comments:
        body = comment.get("body") or ""
        created = comment.get("createdAt") or ""
        if CLAIM_RELEASE in body:
            markers.append((created, "release", None))
        elif CLAIM_BEGIN in body:
            markers.append((created, "claim", parse_claim(body)))
    if not markers:
        return None
    markers.sort(key=lambda m: m[0])
    created, kind, fields = markers[-1]
    if kind == "release" or not fields:
        return None
    at = _as_dt(fields.get("at", "")) or _as_dt(created[:19] + "Z")
    stale = at is None or (now - at) > timedelta(hours=ttl_hours)
    return {**fields, "stale": stale, "age_hours": round((now - at).total_seconds() / 3600, 1) if at else None}


def fetch_comments(number: int, *, runner: Runner = subprocess.run) -> list[dict[str, Any]]:
    proc = run_gh(
        ["issue", "view", str(number), "--repo", repo_slug(), "--json", "comments"],
        runner=runner,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh issue view {number} failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout or "{}").get("comments") or []


def live_claims(issues: list[dict[str, Any]], *, now: datetime) -> dict[int, dict[str, Any]]:
    """Claims in force, keyed by issue number.

    Only issues carrying the label are inspected: the label is the cheap
    filter that keeps `next` from fetching comments for the whole backlog.
    """
    out: dict[int, dict[str, Any]] = {}
    for issue in issues:
        if CLAIM_LABEL not in label_names(issue):
            continue
        claim = active_claim(fetch_comments(int(issue["number"])), now=now)
        if claim and not claim["stale"]:
            out[int(issue["number"])] = claim
    return out


def stale_claims(issues: list[dict[str, Any]], *, now: datetime) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for issue in issues:
        if CLAIM_LABEL not in label_names(issue):
            continue
        claim = active_claim(fetch_comments(int(issue["number"])), now=now)
        if claim and claim["stale"]:
            out[int(issue["number"])] = claim
    return out


def resolve_batch(pkg: dict[str, Any], index: int | None) -> tuple[int, dict[str, Any]]:
    batches = pkg.get("prs", [])
    if not batches:
        raise RuntimeError(f"package {pkg['slug']} has no PR batches to claim")
    if index is None:
        index = 0
    if not 0 <= index < len(batches):
        raise RuntimeError(f"batch {index} out of range for {pkg['slug']} (0..{len(batches) - 1})")
    return index, batches[index]


# --------------------------------------------------------------------------
# "what do I work on next?"
# --------------------------------------------------------------------------


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

    Gated packages are skipped rather than returned, so a session never opens
    on work it cannot finish -- but they are returned alongside so the caller
    can surface the decision instead of hiding it.

    A package whose every startable batch is already claimed is skipped too,
    which is what makes two concurrent agents fan out across packages instead
    of colliding on the top-ranked one.
    """
    held = set(claimed)
    skipped: list[dict[str, Any]] = []
    for pkg in packages:
        if not (set(pkg["issues"]) & open_numbers):
            continue
        if pkg.get("readiness") != READY:
            skipped.append(pkg)
            continue
        if next_pr(pkg, open_numbers, held) is None:
            skipped.append(dict(pkg, _skip_reason="every startable batch is already claimed"))
            continue
        return pkg, skipped
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


def render_next(
    pkg: dict[str, Any] | None,
    pr: dict[str, Any] | None,
    skipped: list[dict[str, Any]],
    open_numbers: set[int],
    titles: dict[int, str],
) -> str:
    if pkg is None:
        lines = ["No startable package: every ready-now package is complete."]
        if skipped:
            lines += ["", "Everything left is gated or already claimed:"]
            for gated in skipped:
                why = gated.get("_skip_reason") or gated.get("gate") or "see the issues"
                lines.append(f"  [{gated['rank']}] {gated['title']} ({gated['readiness']})")
                lines.append(f"      {why}")
        return "\n".join(lines)

    remaining = sorted(set(pkg["issues"]) & open_numbers)
    lines = [
        f"NEXT: {pkg['title']}",
        "",
        pkg["objective"],
        "",
        f"Open in this package ({len(remaining)}):",
    ]
    for number in remaining:
        lines.append(f"  #{number}  {titles.get(number, '')[:70]}")

    if pkg.get("gate"):
        lines += ["", f"GATE (part of this package is blocked): {pkg['gate']}"]

    if pr:
        lines += [
            "",
            "Open ONE pull request for:",
            f"  {pr['title']}",
            f"  resolves: {', '.join('#%d' % n for n in pr['issues'] if n in open_numbers)}",
            f"  why batched: {pr['note']}",
        ]
    else:
        lines += ["", "Every ungated PR in this package is done; the rest is gated."]

    lines += ["", "Package is done when:"]
    for item in pkg.get("done", []):
        lines.append(f"  - {item}")

    if skipped:
        lines += ["", "Ranked higher but not startable:"]
        for gated in skipped:
            why = gated.get("_skip_reason") or gated.get("gate") or gated["readiness"]
            lines.append(f"  [{gated['rank']}] {gated['title']} -- {why}")

    lines += [
        "",
        "Rules: clean branch off origin/master, one ready PR, `Closes #N` only for",
        "fully-resolved issues (`Refs #N` otherwise). Details in BACKLOG.md.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def _severity_bar(bucket: dict[str, Any]) -> str:
    parts = [f"{sev} {bucket[sev]}" for sev in SEVERITIES if bucket.get(sev)]
    if bucket.get("unprioritised"):
        parts.append(f"unprioritised {bucket['unprioritised']}")
    return ", ".join(parts) or "-"


def render_report(data: dict[str, Any]) -> str:
    lines = [f"Nova backlog -- {data['open_issues']} open issues in {data['repo']}", ""]
    for title in data["package_order"]:
        bucket = data["packages"].get(title)
        if not bucket:
            # The inbox is a permanent fixture, not a finished package.
            note = "(empty -- nothing awaiting triage)" if title == INBOX_TITLE else "(milestone can be closed)"
            lines.append(f"  {title:<52} 0 open  {note}")
            continue
        lines.append(f"  {title:<52} {bucket['open']:>2} open  [{_severity_bar(bucket)}]")
    if NO_MILESTONE in data["packages"]:
        bucket = data["packages"][NO_MILESTONE]
        lines.append(f"  {NO_MILESTONE:<52} {bucket['open']:>2} open  [{_severity_bar(bucket)}]")

    lines.append("")
    if data.get("inbox"):
        urgent = data.get("inbox_urgent") or []
        mark = f"   <- {len(urgent)} URGENT: {', '.join('#%d' % n for n in urgent)}" if urgent else ""
        lines.append(
            f"Inbox: {len(data['inbox'])} awaiting routing "
            f"({', '.join('#%d' % n for n in data['inbox'])}){mark}"
        )
        lines.append("  -> py -3 tools/backlog_triage.py triage")
        lines.append("")

    if data["hygiene_gaps"]:
        lines.append(f"Hygiene gaps ({len(data['hygiene_gaps'])} issues):")
        for number, gaps in sorted(data["hygiene_gaps"].items()):
            lines.append(f"  #{number:<5} {', '.join(gaps)}")
    else:
        lines.append("Hygiene: clean -- every open issue is packaged and labelled.")

    if data["drift"]:
        lines += ["", f"Plan drift ({len(data['drift'])}):"]
        lines += [f"  {problem}" for problem in data["drift"]]

    if data["duplicate_aliases"]:
        lines += ["", "Ambiguous legacy D-NNN aliases (cite #NNN instead):"]
        for alias, nums in sorted(data["duplicate_aliases"].items()):
            lines.append(f"  {alias} -> {', '.join('#%d' % n for n in nums)}")

    return "\n".join(lines)


def render_map_section(
    data: dict[str, Any], milestones: list[dict[str, Any]], packages: list[dict[str, Any]]
) -> str:
    """The generated block inside the Backlog Map issue.

    Everything outside the markers is hand-written and preserved.
    """
    by_title = {ms.get("title", ""): ms for ms in milestones}
    by_title_pkg = {p["title"]: p for p in packages}
    active = len([t for t in data["package_order"] if t in data["packages"]])
    lines = [
        MAP_BEGIN,
        "",
        f"**{data['open_issues']} open issues** across {active} active packages. "
        "Generated by `tools/backlog_triage.py sync-map` from GitHub milestones plus "
        "`knowledge/backlog-packages.json` -- edit those, not this block.",
        "",
        "| # | Package | Open | Severity | Ready | Issues |",
        "|---|---------|-----:|----------|-------|--------|",
    ]
    for title in data["package_order"]:
        bucket = data["packages"].get(title)
        ms = by_title.get(title, {})
        pkg = by_title_pkg.get(title, {})
        num = ms.get("number", "")
        link = f"[{title}](https://github.com/{data['repo']}/milestone/{num})" if num else title
        ready = pkg.get("readiness", "?")
        if not bucket:
            state = "_empty_" if title == INBOX_TITLE else "_done_"
            lines.append(f"| {num} | {link} | 0 | - | {ready} | {state} |")
            continue
        issues = " ".join(f"#{n}" for n in bucket["numbers"])
        lines.append(
            f"| {num} | {link} | {bucket['open']} | {_severity_bar(bucket)} | {ready} | {issues} |"
        )

    if NO_MILESTONE in data["packages"]:
        bucket = data["packages"][NO_MILESTONE]
        issues = " ".join(f"#{n}" for n in bucket["numbers"])
        lines.append(f"| - | **{NO_MILESTONE}** | {bucket['open']} | {_severity_bar(bucket)} | - | {issues} |")

    lines.append("")
    if data["hygiene_gaps"]:
        lines += [f"### Triage queue ({len(data['hygiene_gaps'])} issues need a field)", ""]
        lines += ["| Issue | Missing |", "|-------|---------|"]
        for number, gaps in sorted(data["hygiene_gaps"].items()):
            lines.append(f"| #{number} | {', '.join(gaps)} |")
        lines.append("")
    else:
        lines += ["### Triage queue: empty -- every open issue is packaged and labelled.", ""]

    if data["drift"]:
        lines += ["### Plan drift", ""]
        lines += [f"- {problem}" for problem in data["drift"]]
        lines.append("")

    lines.append(MAP_END)
    return "\n".join(lines)


def splice_map(body: str, section: str) -> str:
    """Replace the generated block, or append it if the markers are absent."""
    if MAP_BEGIN in body and MAP_END in body:
        head = body.split(MAP_BEGIN)[0]
        tail = body.split(MAP_END, 1)[1]
        return f"{head}{section}{tail}"
    separator = "\n\n" if body.strip() else ""
    return f"{body.rstrip()}{separator}{section}\n"


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_next(args: argparse.Namespace) -> int:
    issues = fetch_issues()
    packages = with_inbox(load_packages(), issues)
    open_numbers = {int(i["number"]) for i in issues}
    titles = {int(i["number"]): i.get("title", "") for i in issues}
    held = live_claims(issues, now=datetime.now(timezone.utc))
    pkg, skipped = pick_next(packages, open_numbers, held)
    pr = next_pr(pkg, open_numbers, held) if pkg else None

    if args.json:
        print(json.dumps(
            {
                "package": pkg,
                "pull_request": pr,
                "open_in_package": sorted(set(pkg["issues"]) & open_numbers) if pkg else [],
                "skipped_gated": [
                    {
                        "rank": s["rank"],
                        "title": s["title"],
                        "gate": s.get("_skip_reason") or s.get("gate", ""),
                    }
                    for s in skipped
                ],
                "claimed_issues": sorted(held),
            },
            indent=2,
        ))
    else:
        print(render_next(pkg, pr, skipped, open_numbers, titles))
    return EXIT_OK


def cmd_claims(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    issues = fetch_issues()
    labelled = [i for i in issues if CLAIM_LABEL in label_names(i)]
    if not labelled:
        print("No claims held.")
        return EXIT_OK
    rows = []
    for issue in labelled:
        claim = active_claim(fetch_comments(int(issue["number"])), now=now)
        rows.append((int(issue["number"]), issue.get("title", ""), claim))
    for number, title, claim in sorted(rows):
        if claim is None:
            print(f"  #{number}  label set but no claim comment -- run `release` to clear it")
            continue
        state = "STALE" if claim["stale"] else "held"
        print(f"  #{number}  [{state}] {claim.get('agent','?')} on {claim.get('branch','?')} "
              f"(batch {claim.get('batch','?')}, {claim.get('age_hours','?')}h)")
        print(f"      {title[:70]}")
    stale = [r for r in rows if r[2] and r[2]["stale"]]
    if stale:
        print(f"\n{len(stale)} stale claim(s) past {CLAIM_TTL_HOURS}h -- reclaimable with "
              f"`claim --force`, or clear with `release`.")
    return EXIT_OK


def cmd_claim(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    packages = load_packages()
    matches = [p for p in packages if p["slug"] == args.package]
    if not matches:
        print(f"no package with slug {args.package!r}", file=sys.stderr)
        return EXIT_ERROR
    pkg = matches[0]
    index, batch = resolve_batch(pkg, args.batch)
    ref = batch_ref(pkg["slug"], index)
    agent = args.agent or agent_id()
    branch = args.branch or f"agent/{pkg['slug']}-{index}"

    issues = fetch_issues()
    open_numbers = {int(i["number"]) for i in issues}
    targets = [n for n in batch["issues"] if n in open_numbers]
    if not targets:
        print(f"batch {ref} has no open issues left -- nothing to claim.")
        return EXIT_OK

    existing = {}
    for number in targets:
        claim = active_claim(fetch_comments(number), now=now)
        if claim and (not claim["stale"] or args.force):
            if not claim["stale"]:
                existing[number] = claim
    if existing and not args.force:
        for number, claim in existing.items():
            print(f"#{number} already held by {claim.get('agent','?')} "
                  f"on {claim.get('branch','?')} ({claim.get('age_hours','?')}h)", file=sys.stderr)
        print("Pick another batch, or use --force if you know that agent is gone.", file=sys.stderr)
        return EXIT_GAPS

    body = format_claim(agent=agent, batch=ref, branch=branch, at=now)
    for number in targets:
        run_gh(["issue", "edit", str(number), "--repo", repo_slug(), "--add-label", CLAIM_LABEL])
        proc = run_gh(
            ["issue", "comment", str(number), "--repo", repo_slug(), "--body-file", "-"],
            runner=lambda cmd, **kw: subprocess.run(cmd, input=body, **kw),
        )
        if proc.returncode != 0:
            print(f"claim comment on #{number} failed: {proc.stderr.strip()}", file=sys.stderr)
            return EXIT_ERROR

    # Claim-then-verify: GitHub has no compare-and-swap, so two agents can both
    # have read "unclaimed". Earliest `at` wins; a loser yields immediately
    # rather than working a batch someone else also started.
    others = [
        c for c in (active_claim(fetch_comments(n), now=now) for n in targets)
        if c and c.get("agent") and c["agent"] != agent and not c["stale"]
    ]
    if others:
        earliest_other = min(others, key=lambda c: c.get("at", ""))
        if earliest_other.get("at", "") < now.strftime("%Y-%m-%dT%H:%M:%SZ"):
            print(f"Race lost: {earliest_other.get('agent')} claimed {ref} first. Yielding.",
                  file=sys.stderr)
            for number in targets:
                run_gh(["issue", "comment", str(number), "--repo", repo_slug(), "--body-file", "-"],
                       runner=lambda cmd, **kw: subprocess.run(
                           cmd, input=format_release(agent=agent, batch=ref), **kw))
            return EXIT_GAPS

    print(f"Claimed {ref} ({', '.join('#%d' % n for n in targets)}) as {agent} on {branch}.")
    print(f"Release with: py -3 tools/backlog_triage.py release --package {pkg['slug']} --batch {index}")
    return EXIT_OK


def cmd_release(args: argparse.Namespace) -> int:
    packages = load_packages()
    matches = [p for p in packages if p["slug"] == args.package]
    if not matches:
        print(f"no package with slug {args.package!r}", file=sys.stderr)
        return EXIT_ERROR
    pkg = matches[0]
    index, batch = resolve_batch(pkg, args.batch)
    ref = batch_ref(pkg["slug"], index)
    agent = args.agent or agent_id()
    body = format_release(agent=agent, batch=ref)
    issues = fetch_issues()
    open_numbers = {int(i["number"]) for i in issues}
    for number in batch["issues"]:
        if number not in open_numbers:
            continue  # closed issues carry no claim worth clearing
        run_gh(["issue", "edit", str(number), "--repo", repo_slug(), "--remove-label", CLAIM_LABEL])
        run_gh(["issue", "comment", str(number), "--repo", repo_slug(), "--body-file", "-"],
               runner=lambda cmd, **kw: subprocess.run(cmd, input=body, **kw))
    print(f"Released {ref}.")
    return EXIT_OK


def cmd_triage(args: argparse.Namespace) -> int:
    packages = load_packages()
    issues = fetch_issues()
    by_number = {int(i["number"]): i for i in issues}
    inbox = [i for i in issues if milestone_title(i) == INBOX_TITLE]
    if args.json:
        print(json.dumps(
            [
                {
                    "number": int(i["number"]),
                    "title": i.get("title", ""),
                    "severity": severity_of(i),
                    "domains": sorted(domain_labels(i)),
                    "suggestions": candidate_packages(i, packages, by_number),
                }
                for i in inbox
            ],
            indent=2,
        ))
    else:
        print(render_triage(inbox, packages, by_number))
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    data = analyse(fetch_issues(), fetch_milestones(), load_packages())
    print(json.dumps(data, indent=2, sort_keys=True) if args.json else render_report(data))
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    data = analyse(fetch_issues(), fetch_milestones(), load_packages())
    print(render_report(data))
    urgent = data.get("inbox_urgent") or []
    problems = len(data["hygiene_gaps"]) + len(data["drift"]) + len(urgent)
    if problems:
        print("", file=sys.stderr)
        if urgent:
            print(
                "FAIL: untriaged P0/P1 -- "
                + ", ".join(f"#{n}" for n in urgent)
                + ". Route these before any other work.",
                file=sys.stderr,
            )
        if data["hygiene_gaps"] or data["drift"]:
            print(
                f"FAIL: {len(data['hygiene_gaps'])} issues missing a package or label, "
                f"{len(data['drift'])} plan/GitHub mismatches. See the triage step in BACKLOG.md.",
                file=sys.stderr,
            )
        return EXIT_GAPS
    return EXIT_OK


def cmd_sync(args: argparse.Namespace) -> int:
    """Project the authored packages onto GitHub milestones and issue assignments."""
    packages = load_packages()
    existing = {ms.get("title", ""): ms for ms in fetch_milestones()}
    issues = fetch_issues()
    by_number = {int(i["number"]): i for i in issues}
    actions: list[str] = []

    for pkg in packages:
        title = pkg["title"]
        description = milestone_description(pkg)
        found = existing.get(title)
        if found is None:
            actions.append(f"create milestone {title!r}")
            if not args.dry_run:
                proc = run_gh([
                    "api", "--method", "POST", f"repos/{repo_slug()}/milestones",
                    "-f", f"title={title}", "-f", f"description={description}",
                ])
                if proc.returncode != 0:
                    print(f"create milestone failed: {proc.stderr.strip()}", file=sys.stderr)
                    return EXIT_ERROR
                existing[title] = json.loads(proc.stdout)
        elif (found.get("description") or "") != description:
            actions.append(f"update milestone {title!r} description")
            if not args.dry_run:
                proc = run_gh([
                    "api", "--method", "PATCH",
                    f"repos/{repo_slug()}/milestones/{found['number']}",
                    "-f", f"description={description}",
                ])
                if proc.returncode != 0:
                    print(f"update milestone failed: {proc.stderr.strip()}", file=sys.stderr)
                    return EXIT_ERROR

        for number in pkg["issues"]:
            issue = by_number.get(number)
            if issue is None:
                continue  # closed since the plan was authored; not an error
            if milestone_title(issue) == title:
                continue
            actions.append(f"assign #{number} -> {title!r}")
            if not args.dry_run:
                proc = run_gh([
                    "issue", "edit", str(number), "--repo", repo_slug(), "--milestone", title,
                ])
                if proc.returncode != 0:
                    print(f"assign #{number} failed: {proc.stderr.strip()}", file=sys.stderr)
                    return EXIT_ERROR

    if not actions:
        print("Milestones already match the plan.")
        return EXIT_OK
    prefix = "would " if args.dry_run else ""
    for action in actions:
        print(f"{prefix}{action}")
    print(f"\n{len(actions)} change(s){' (dry run)' if args.dry_run else ''}.")
    return EXIT_OK


def cmd_sync_map(args: argparse.Namespace) -> int:
    milestones = fetch_milestones()
    packages = load_packages()
    data = analyse(fetch_issues(), milestones, packages)
    section = render_map_section(data, milestones, packages)

    proc = run_gh(["issue", "view", str(args.issue), "--repo", repo_slug(), "--json", "body"])
    if proc.returncode != 0:
        print(f"gh issue view failed: {proc.stderr.strip()}", file=sys.stderr)
        return EXIT_ERROR
    current = json.loads(proc.stdout or "{}").get("body") or ""
    updated = splice_map(current, section)

    if updated == current:
        print(f"Backlog Map #{args.issue} already current.")
        return EXIT_OK
    if args.dry_run:
        print(updated)
        return EXIT_OK

    edit = run_gh(
        ["issue", "edit", str(args.issue), "--repo", repo_slug(), "--body-file", "-"],
        runner=lambda cmd, **kw: subprocess.run(cmd, input=updated, **kw),
    )
    if edit.returncode != 0:
        print(f"gh issue edit failed: {edit.stderr.strip()}", file=sys.stderr)
        return EXIT_ERROR
    print(f"Backlog Map #{args.issue} refreshed.")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nova backlog triage (packages, milestones, labels)")
    sub = parser.add_subparsers(dest="command", required=True)

    nxt = sub.add_parser("next", help="the one package and PR to start now")
    nxt.add_argument("--json", action="store_true")
    nxt.set_defaults(func=cmd_next)

    clm = sub.add_parser("claims", help="who is holding which batch")
    clm.set_defaults(func=cmd_claims)

    cla = sub.add_parser("claim", help="claim a PR batch before working it")
    cla.add_argument("--package", required=True, help="package slug")
    cla.add_argument("--batch", type=int, default=None, help="batch index (default 0)")
    cla.add_argument("--agent", default=None, help="agent id (default $NOVA_AGENT_ID)")
    cla.add_argument("--branch", default=None, help="branch you will work on")
    cla.add_argument("--force", action="store_true", help="take over a stale claim")
    cla.set_defaults(func=cmd_claim)

    rel = sub.add_parser("release", help="release a batch you claimed")
    rel.add_argument("--package", required=True)
    rel.add_argument("--batch", type=int, default=None)
    rel.add_argument("--agent", default=None)
    rel.set_defaults(func=cmd_release)

    tri = sub.add_parser("triage", help="list inbox issues with routing context")
    tri.add_argument("--json", action="store_true")
    tri.set_defaults(func=cmd_triage)

    rep = sub.add_parser("report", help="package rollup, hygiene gaps and plan drift")
    rep.add_argument("--json", action="store_true")
    rep.set_defaults(func=cmd_report)

    chk = sub.add_parser("check", help="same as report, but exit 1 on gaps or drift")
    chk.set_defaults(func=cmd_check)

    syn = sub.add_parser("sync", help="project packages onto milestones and issue assignments")
    syn.add_argument("--dry-run", action="store_true")
    syn.set_defaults(func=cmd_sync)

    smap = sub.add_parser("sync-map", help="refresh the generated block in the Backlog Map issue")
    smap.add_argument("--issue", type=int, required=True)
    smap.add_argument("--dry-run", action="store_true")
    smap.set_defaults(func=cmd_sync_map)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
