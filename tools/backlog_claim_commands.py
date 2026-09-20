"""GitHub mutations and inspection for advisory backlog batch claims.

Separated from read-only selection commands under ADR 001. Claims remain
advisory; footprint conflicts use the same pure check as the picker.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone

from tools.backlog_branches import (
    delete_unused_branch,
    ensure_linked_branch,
    last_commit_at,
)
from tools.backlog_claims import (
    CLAIM_LABEL,
    CLAIM_TTL_HOURS,
    active_claim,
    agent_id,
    batch_ref,
    claim_for,
    format_claim,
    format_release,
    live_claims,
    resolve_batch,
    resolve_claim,
)
from tools.backlog_footprints import (
    OVERLAP_REASON,
    batch_touches,
    claim_conflicts,
    conflict_lines,
)
from tools.backlog_github import (
    EXIT_ERROR,
    EXIT_GAPS,
    EXIT_OK,
    fetch_comments,
    fetch_issues,
    label_names,
    repo_slug,
    run_gh,
)
from tools.backlog_plan import load_packages, with_inbox


def branch_activity_for(ref: str):
    """Last commit on a claimed branch, for the staleness decision.

    A module-level function rather than a lambda so tests can replace it and
    so every enforcement path shares one definition of "still working".
    """
    return last_commit_at(run_gh, repo_slug(), ref)


def post_release(targets: list[int], *, agent: str, batch: str) -> None:
    """Withdraw a claim: release marker plus the label that advertised it.

    The label is half the claim -- `live_claims` uses it as its cheap filter
    and `claims` lists it -- so dropping only the comment leaves issues
    reading `claimed` with nothing behind them.

    A concurrent winner may have claimed the same issues after us, and their
    claim comment is then newer than our release. The label is theirs at that
    point, so it is removed only once no claim survives on the issue.
    """
    body = format_release(agent=agent, batch=batch)
    for number in targets:
        run_gh(["issue", "comment", str(number), "--repo", repo_slug(), "--body-file", "-"],
               runner=lambda cmd, **kw: subprocess.run(cmd, input=body, **kw))
        if active_claim(fetch_comments(number), now=datetime.now(timezone.utc)) is None:
            run_gh(["issue", "edit", str(number), "--repo", repo_slug(),
                    "--remove-label", CLAIM_LABEL])


def cmd_claims(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    issues = fetch_issues()
    labelled = [i for i in issues if CLAIM_LABEL in label_names(i)]
    if not labelled:
        print("No claims held.")
        return EXIT_OK
    rows = []
    for issue in labelled:
        number = int(issue["number"])
        # The claim names the branch; the branch says whether the holder is
        # still working. A comment alone cannot tell those apart.
        claim = resolve_claim(fetch_comments(number), now=now,
                              branch_activity_for=branch_activity_for)
        rows.append((number, issue.get("title", ""), claim))
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
    if getattr(args, "conflicts", False):
        held = {n: c for n, _, c in rows if c and not c["stale"]}
        packages = with_inbox(load_packages(), issues)
        opened = {int(i["number"]) for i in issues}
        found = False
        for pkg in packages:
            for index, batch in enumerate(pkg.get("prs", [])):
                if batch.get("gated") or not set(batch["issues"]) & opened:
                    continue
                # Do not report a batch as conflicting with its own holder.
                others = {n: c for n, c in held.items() if c.get("batch") != batch_ref(pkg["slug"], index)}
                conflicts = claim_conflicts(pkg, batch, others, packages)
                if conflicts:
                    found = True
                    print(f"\n{batch_ref(pkg['slug'], index)} -- {OVERLAP_REASON}:")
                    for line in conflict_lines(conflicts):
                        print(f"  {line}")
        if not found:
            print("\nNo cross-batch file conflicts with live claims.")
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
    if batch.get("gated"):
        print("This batch is gated on an operator decision.", file=sys.stderr)
        return EXIT_GAPS

    issues = fetch_issues()
    open_numbers = {int(i["number"]) for i in issues}
    targets = [n for n in batch["issues"] if n in open_numbers]
    if not targets:
        print(f"batch {ref} has no open issues left -- nothing to claim.")
        return EXIT_OK

    existing = {}
    for number in targets:
        claim = resolve_claim(fetch_comments(number), now=now,
                              branch_activity_for=branch_activity_for)
        if claim and (not claim["stale"] or args.force):
            if not claim["stale"]:
                existing[number] = claim
    if existing:
        for number, claim in existing.items():
            print(f"#{number} already held by {claim.get('agent','?')} "
                  f"on {claim.get('branch','?')} ({claim.get('age_hours','?')}h)", file=sys.stderr)
        print("Pick another batch, or release the live claim after coordinating with its owner.", file=sys.stderr)
        return EXIT_GAPS

    held = live_claims(issues, now=now, branch_activity_for=branch_activity_for)
    # Refreshing our own claim is allowed; a different live holder is not.
    others = {n: c for n, c in held.items()
              if (c.get("agent"), c.get("batch"), c.get("branch")) != (agent, ref, branch)}
    conflicts = claim_conflicts(pkg, batch, others, packages)
    if conflicts:
        print(OVERLAP_REASON + ":", file=sys.stderr)
        for line in conflict_lines(conflicts):
            print("  " + line, file=sys.stderr)
        return EXIT_GAPS
    body = format_claim(agent=agent, batch=ref, branch=branch, at=now,
                        touches=batch_touches(pkg, batch))
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
        c for c in (resolve_claim(fetch_comments(n), now=now,
                                  branch_activity_for=branch_activity_for) for n in targets)
        if c and c.get("agent") and c["agent"] != agent and not c["stale"]
    ]
    if others:
        earliest_other = min(others, key=lambda c: c.get("at", ""))
        if earliest_other.get("at", "") < now.strftime("%Y-%m-%dT%H:%M:%SZ"):
            print(f"Race lost: {earliest_other.get('agent')} claimed {ref} first. Yielding.",
                  file=sys.stderr)
            post_release(targets, agent=agent, batch=ref)
            return EXIT_GAPS

    # Different issues can race on the same files. Re-fetch the label list
    # as well as comments; the pre-claim snapshot cannot see the new holder.
    live = live_claims(fetch_issues(), now=datetime.now(timezone.utc),
                       branch_activity_for=branch_activity_for)
    others_by_issue = {n: c for n, c in live.items()
                       if (c.get("agent"), c.get("batch"), c.get("branch")) != (agent, ref, branch)}
    conflicts = claim_conflicts(pkg, batch, others_by_issue, packages)
    own_order = (now.strftime("%Y-%m-%dT%H:%M:%SZ"), agent, ref, branch)
    earlier = [c for c in conflicts if (c["at"], c["agent"], c["batch"], c["branch"]) < own_order]
    if earlier:
        post_release(targets, agent=agent, batch=ref)
        print("Race lost: " + OVERLAP_REASON + "; yielding to " +
              "; ".join(conflict_lines(earlier)), file=sys.stderr)
        return EXIT_GAPS

    # Only now, with the batch genuinely ours, cut the branch: a losing agent
    # must not leave an orphan ref on origin. A claim that cannot produce its
    # branch is withdrawn -- the whole point is that `claimed` implies a branch
    # someone can fetch.
    anchor = min(targets)
    link = ensure_linked_branch(
        run_gh, repo_slug(), anchor=anchor, branch=branch,
        extra_issues=tuple(n for n in sorted(targets) if n != anchor),
    )
    if not link.ok:
        post_release(targets, agent=agent, batch=ref)
        reason = ("this token cannot write branches" if link.denied
                  else link.error or "unknown failure")
        print(f"Claim withdrawn: {branch} is not on origin ({reason}).", file=sys.stderr)
        print("A claim now has to name a branch that exists. Fix the branch name "
              "or the token, then claim again.", file=sys.stderr)
        return EXIT_ERROR

    print(f"Claimed {ref} ({', '.join('#%d' % n for n in targets)}) as {agent} on {branch}.")
    where = (f"linked from #{anchor}" if anchor in link.linked else "no Development link")
    print(f"Branch {branch} on origin at {link.tip[:7]} ({where}).")
    print(f"  git fetch origin && git checkout {branch}")
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
    issues = fetch_issues()
    open_numbers = {int(i["number"]) for i in issues}
    targets = [n for n in batch["issues"] if n in open_numbers]

    # The branch to clean up is the one the claim recorded, not one the caller
    # remembers: the claim comment is the only record that survives a crash.
    # R5: the branch WE claimed, never the elected holder's. With two
    # surviving holders the election returns the other agent, and cleaning up
    # their branch deletes the ref their live claim points at.
    branch = getattr(args, "branch", None)
    for number in targets:
        if branch:
            break
        mine = claim_for(fetch_comments(number), agent=agent, batch=ref)
        if mine:
            branch = mine.get("branch")

    # closed issues carry no claim worth clearing; post_release drops the label
    post_release(targets, agent=agent, batch=ref)
    print(f"Released {ref}.")

    if branch and not getattr(args, "keep_branch", False):
        # Untouched branches are litter; a branch with commits is someone's
        # work and outlives the claim that named it (#369).
        delete_unused_branch(run_gh, repo_slug(), branch)
    return EXIT_OK
