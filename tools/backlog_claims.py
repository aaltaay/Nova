"""Cross-tool advisory claims on a backlog PR batch.

Agents run from several tools (Claude Code, Codex, Cursor) and all of them
authenticate as the same GitHub account, so `assignee` cannot say WHO holds a
piece of work. GitHub is the only substrate every tool can see, so the claim
lives there: a `claimed` label for cheap filtering plus a structured comment
carrying agent id, branch and timestamp.

The lock unit is the PR BATCH, not the issue -- the batch is already the unit
of work, so locking per-issue would create four locks for one job.

The claim is the lock; the branch it names is the proof (see
`backlog_branches`). A claim that cannot cut its branch is withdrawn, so the
`claimed` label never outlives a ref nobody can fetch.

This is ADVISORY. Two agents can both read "unclaimed" before either writes;
GitHub offers no compare-and-swap on labels. The `claim` command therefore
re-reads after writing and yields if an earlier live claim exists (earliest
`at` wins), which makes a collision detectable and resolvable rather than
impossible. An agent that ignores the protocol will still collide."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from tools.backlog_footprints import normalize_touches
from tools.backlog_github import fetch_comments, label_names

CLAIM_LABEL = "claimed"

# Long enough for a real session on a multi-issue batch, short enough that a
# crashed agent does not block a package for a working day.
CLAIM_TTL_HOURS = 4

CLAIM_BEGIN = "<!-- nova-claim"
CLAIM_RELEASE = "<!-- nova-claim-release"
CLAIM_END = "-->"


def agent_id() -> str:
    """Self-reported. Cooperative, not adversarial -- nobody is defending
    against a hostile agent, only stopping honest ones duplicating work."""
    return os.environ.get("NOVA_AGENT_ID") or "unknown-agent"


def batch_ref(slug: str, index: int) -> str:
    return f"{slug}#{index}"


def format_claim(
    *, agent: str, batch: str, branch: str, at: datetime,
    touches: list[str] | None = None,
) -> str:
    footprint = f"touches: {json.dumps(normalize_touches(touches))}\n" if touches is not None else ""
    return (
        f"{CLAIM_BEGIN}\n"
        f"agent: {agent}\n"
        f"batch: {batch}\n"
        f"branch: {branch}\n"
        f"at: {at.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"{footprint}"
        f"{CLAIM_END}\n"
        f"Claimed by `{agent}` on branch `{branch}` for batch `{batch}`. "
        f"Stale {CLAIM_TTL_HOURS}h after the newer of this claim and the last "
        f"commit on `{branch}` -- `py -3 tools/backlog_triage.py claims` lists holders."
    )


def format_release(*, agent: str, batch: str) -> str:
    """A release names its releaser, because it only clears that agent's claim.

    Without the agent a release is anonymous, and the loser of a race yielding
    reads as "this issue is free" -- which then withdraws the winner's label
    and hides their live claim from `next`.
    """
    return (
        f"{CLAIM_RELEASE}\n"
        f"agent: {agent}\n"
        f"batch: {batch}\n"
        f"{CLAIM_END}\n"
        f"Released by `{agent}` (batch `{batch}`)."
    )


def _fields(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def parse_release(body: str) -> dict[str, str] | None:
    """Fields of a release marker. ``{}`` for a legacy one, which named nobody.

    `CLAIM_BEGIN` is a prefix of `CLAIM_RELEASE`, so every caller must test for
    a release *before* treating a comment as a claim.
    """
    if CLAIM_RELEASE not in body:
        return None
    return _fields(body.split(CLAIM_RELEASE, 1)[1].split(CLAIM_END, 1)[0])


def parse_claim(body: str) -> dict[str, str] | None:
    """Pull the structured block out of a claim comment. None if absent."""
    if CLAIM_BEGIN not in body:
        return None
    fields = _fields(body.split(CLAIM_BEGIN, 1)[1].split(CLAIM_END, 1)[0])
    return fields or None


def _as_dt(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def active_claim(
    comments: list[dict[str, Any]], *, now: datetime, ttl_hours: int = CLAIM_TTL_HOURS,
    branch_activity: datetime | None = None,
) -> dict[str, Any] | None:
    """The claim in force on an issue, or None.

    The newest marker wins: a release after a claim clears it. A claim older
    than the TTL is reported with ``stale: True`` rather than hidden, so a
    caller can decide between reclaiming and reporting.

    ``branch_activity`` is the last commit time on the claimed branch, which
    only a caller can fetch -- this stays pure (ADR 003). Given it, an agent
    four hours into real work reads as live instead of looking identical to one
    that died at minute two. Omitted, the answer is exactly what it always was.
    """
    markers: list[tuple[str, str, dict[str, str]]] = []
    for comment in comments:
        body = comment.get("body") or ""
        created = comment.get("createdAt") or ""
        # CLAIM_BEGIN is a prefix of CLAIM_RELEASE: release first, always.
        if CLAIM_RELEASE in body:
            markers.append((created, "release", parse_release(body) or {}))
        elif CLAIM_BEGIN in body:
            markers.append((created, "claim", parse_claim(body) or {}))
    if not markers:
        return None
    markers.sort(key=lambda m: m[0])

    # A release that names nobody predates identity-aware releases and keeps
    # its old meaning: it clears the issue outright, up to its own timestamp.
    anonymous_release = ""
    for created, kind, fields in markers:
        if kind == "release" and not fields.get("agent"):
            anonymous_release = created

    # Otherwise each agent's newest marker decides whether THEY still hold.
    # A losing agent yielding must not clear the winner's claim: two agents
    # can hold markers on one issue, and only their own release speaks for them.
    latest: dict[str, tuple[str, str, dict[str, str]]] = {}
    for created, kind, fields in markers:
        if anonymous_release and created <= anonymous_release:
            continue
        latest[fields.get("agent", "")] = (created, kind, fields)

    holders = [(created, fields) for created, kind, fields in latest.values()
               if kind == "claim" and fields]
    if not holders:
        return None
    # Earliest claim wins, the same rule claim-then-verify applies to a race.
    created, fields = min(holders, key=lambda h: (h[1].get("at", ""), h[0]))
    at = _as_dt(fields.get("at", "")) or _as_dt(created[:19] + "Z")
    # Work on the branch renews the claim; the comment is only where it started.
    last = max([t for t in (at, branch_activity) if t is not None], default=None)
    stale = last is None or (now - last) > timedelta(hours=ttl_hours)
    return {**fields, "stale": stale,
            "age_hours": round((now - last).total_seconds() / 3600, 1) if last else None}


def resolve_claim(
    comments: list[dict[str, Any]], *, now: datetime,
    branch_activity_for: Callable[[str], datetime | None] | None = None,
) -> dict[str, Any] | None:
    """`active_claim`, with the branch consulted only when it can change the answer.

    Every path that decides whether a batch is held must go through here, or
    `claims` and `next` disagree about who is working: a holder six hours in
    but committing would read as held on the display and stale to the picker,
    which hands the same batch to a second agent.

    Branch activity can only ever revive a claim -- staleness takes the newer
    of the two -- so a claim that is live on comment age needs no lookup at
    all, and `next` pays one call only for the rare stale-looking holder.
    """
    claim = active_claim(comments, now=now)
    if claim and claim["stale"] and branch_activity_for and claim.get("branch"):
        claim = active_claim(comments, now=now,
                             branch_activity=branch_activity_for(claim["branch"]))
    return claim


def _claims_where(
    issues: list[dict[str, Any]], *, now: datetime, stale: bool,
    branch_activity_for: Callable[[str], datetime | None] | None,
) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for issue in issues:
        if CLAIM_LABEL not in label_names(issue):
            continue
        number = int(issue["number"])
        claim = resolve_claim(fetch_comments(number), now=now,
                              branch_activity_for=branch_activity_for)
        if claim and claim["stale"] is stale:
            out[number] = claim
    return out


def live_claims(
    issues: list[dict[str, Any]], *, now: datetime,
    branch_activity_for: Callable[[str], datetime | None] | None = None,
) -> dict[int, dict[str, Any]]:
    """Claims in force, keyed by issue number.

    Only issues carrying the label are inspected: the label is the cheap
    filter that keeps `next` from fetching comments for the whole backlog.

    This is the enforcement path -- `next` skips what it returns -- so callers
    that can reach GitHub pass ``branch_activity_for`` and get the same answer
    the `claims` view shows.
    """
    return _claims_where(issues, now=now, stale=False,
                         branch_activity_for=branch_activity_for)


def stale_claims(
    issues: list[dict[str, Any]], *, now: datetime,
    branch_activity_for: Callable[[str], datetime | None] | None = None,
) -> dict[int, dict[str, Any]]:
    return _claims_where(issues, now=now, stale=True,
                         branch_activity_for=branch_activity_for)


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
