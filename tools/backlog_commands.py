"""Command implementations for tools/backlog_triage.py.

Split from the CLI so neither file exceeds the 400-line limit in AGENTS.md
2.3. Each function takes the parsed argparse namespace and returns an exit
code; the argument parser itself lives in backlog_triage.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

from tools.backlog_claims import (
    CLAIM_LABEL,
    CLAIM_TTL_HOURS,
    active_claim,
    agent_id,
    batch_ref,
    format_claim,
    format_release,
    live_claims,
    resolve_batch,
)
from tools.backlog_github import (
    EXIT_ERROR,
    EXIT_GAPS,
    EXIT_OK,
    INBOX_TITLE,
    domain_labels,
    fetch_comments,
    fetch_issues,
    fetch_milestones,
    label_names,
    milestone_title,
    repo_slug,
    run_gh,
    severity_of,
)
from tools.backlog_plan import (
    analyse,
    candidate_packages,
    load_packages,
    milestone_description,
    next_pr,
    pick_next,
    with_inbox,
)
from tools.backlog_render import (
    render_map_section,
    render_next,
    render_report,
    render_triage,
    splice_map,
)


def cmd_next(args: argparse.Namespace) -> int:
    issues = fetch_issues()
    packages = with_inbox(load_packages(), issues)
    open_numbers = {int(i["number"]) for i in issues}
    titles = {int(i["number"]): i.get("title", "") for i in issues}
    held = live_claims(issues, now=datetime.now(timezone.utc))
    if getattr(args, "package", None):
        # An explicit package still needs LIVE open/closed state, which the
        # authored JSON does not carry -- without this a caller would dispatch
        # agents at batches whose issues are already closed.
        chosen = [p for p in packages if p["slug"] == args.package]
        if not chosen:
            print(f"no package with slug {args.package!r}", file=sys.stderr)
            return EXIT_ERROR
        pkg, skipped = chosen[0], []
        if not set(pkg["issues"]) & open_numbers:
            pkg = None
    else:
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


