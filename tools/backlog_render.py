"""Text the backlog tools print: the `next` brief, the triage queue, the
package report, and the generated block inside the Backlog Map issue.

Pure. Everything here takes already-fetched data and returns a string, so the
wording can be tested without touching GitHub."""

from __future__ import annotations

from typing import Any

from tools.backlog_github import (
    INBOX_TITLE,
    NO_MILESTONE,
    SEVERITIES,
    URGENT,
    domain_labels,
    severity_of,
)
from tools.backlog_plan import candidate_packages

MAP_BEGIN = "<!-- backlog-map:begin -->"
MAP_END = "<!-- backlog-map:end -->"


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

def render_next(
    pkg: dict[str, Any] | None,
    pr: dict[str, Any] | None,
    skipped: list[dict[str, Any]],
    open_numbers: set[int],
    titles: dict[int, str],
) -> str:
    if pkg is None:
        lines = ["No startable package: ready work is complete or blocked."]
        if skipped:
            lines += ["", "Everything left is gated or already claimed, or overlaps held files:"]
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
        "fully-resolved issues (`Refs #N` otherwise). Details in GitHub Issues/milestones.",
    ]
    return "\n".join(lines)


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
