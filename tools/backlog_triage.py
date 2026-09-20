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
        "empty_packages": [t for t in order if t not in counts],
        "hygiene_gaps": gaps,
        "duplicate_aliases": duplicate_aliases(issues),
        "unpackaged": sorted(
            int(i["number"]) for i in issues if milestone_title(i) == NO_MILESTONE
        ),
        "drift": plan_drift(packages, issues) if packages else [],
    }


# --------------------------------------------------------------------------
# "what do I work on next?"
# --------------------------------------------------------------------------


def pick_next(
    packages: list[dict[str, Any]], open_numbers: set[int]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The highest-ranked package an agent can actually start, plus what it skipped.

    Gated packages are skipped rather than returned, so a session never opens
    on work it cannot finish -- but they are returned alongside so the caller
    can surface the decision instead of hiding it.
    """
    skipped: list[dict[str, Any]] = []
    for pkg in packages:
        if not (set(pkg["issues"]) & open_numbers):
            continue
        if pkg.get("readiness") != READY:
            skipped.append(pkg)
            continue
        return pkg, skipped
    return None, skipped


def next_pr(pkg: dict[str, Any], open_numbers: set[int]) -> dict[str, Any] | None:
    """The first ungated PR batch in this package with open issues left."""
    for pr in pkg.get("prs", []):
        if pr.get("gated"):
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
            lines += ["", "Everything left is gated on a decision:"]
            for gated in skipped:
                lines.append(f"  [{gated['rank']}] {gated['title']} ({gated['readiness']})")
                lines.append(f"      GATE: {gated.get('gate') or 'see the issues'}")
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
            lines.append(f"  [{gated['rank']}] {gated['title']} -- {gated.get('gate') or gated['readiness']}")

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
            lines.append(f"  {title:<52} 0 open  (milestone can be closed)")
            continue
        lines.append(f"  {title:<52} {bucket['open']:>2} open  [{_severity_bar(bucket)}]")
    if NO_MILESTONE in data["packages"]:
        bucket = data["packages"][NO_MILESTONE]
        lines.append(f"  {NO_MILESTONE:<52} {bucket['open']:>2} open  [{_severity_bar(bucket)}]")

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
            lines.append(f"| {num} | {link} | 0 | - | {ready} | _done_ |")
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
    packages = load_packages()
    issues = fetch_issues()
    open_numbers = {int(i["number"]) for i in issues}
    titles = {int(i["number"]): i.get("title", "") for i in issues}
    pkg, skipped = pick_next(packages, open_numbers)
    pr = next_pr(pkg, open_numbers) if pkg else None

    if args.json:
        print(json.dumps(
            {
                "package": pkg,
                "pull_request": pr,
                "open_in_package": sorted(set(pkg["issues"]) & open_numbers) if pkg else [],
                "skipped_gated": [
                    {"rank": s["rank"], "title": s["title"], "gate": s.get("gate", "")}
                    for s in skipped
                ],
            },
            indent=2,
        ))
    else:
        print(render_next(pkg, pr, skipped, open_numbers, titles))
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    data = analyse(fetch_issues(), fetch_milestones(), load_packages())
    print(json.dumps(data, indent=2, sort_keys=True) if args.json else render_report(data))
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    data = analyse(fetch_issues(), fetch_milestones(), load_packages())
    print(render_report(data))
    problems = len(data["hygiene_gaps"]) + len(data["drift"])
    if problems:
        print("", file=sys.stderr)
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
