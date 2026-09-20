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


# ---------------------------------------------------------------------------
# Resolution -- the normative rules R1-R5 live in
# `.cursor/rules/claim-resolution.mdc`, and their executable form is the state
# table in `tools/test_backlog_claims_table.py`. They are deliberately NOT
# restated here: three patches to this logic each fixed one scenario and broke
# another, and prose duplicated beside code is how a rule and its behaviour
# drift apart. Change the table first; an edit here that the table still
# passes has not been reasoned about.
# ---------------------------------------------------------------------------


def _markers(comments: list[dict[str, Any]]) -> list[tuple[str, str, dict[str, str]]]:
    out: list[tuple[str, str, dict[str, str]]] = []
    for comment in comments:
        body = comment.get("body") or ""
        created = comment.get("createdAt") or ""
        # CLAIM_BEGIN is a prefix of CLAIM_RELEASE: test for a release first.
        if CLAIM_RELEASE in body:
            out.append((created, "release", parse_release(body) or {}))
        elif CLAIM_BEGIN in body:
            out.append((created, "claim", parse_claim(body) or {}))
    out.sort(key=lambda m: m[0])
    return out


def _surviving(markers: list[tuple[str, str, dict[str, str]]]) -> list[tuple[str, dict[str, str]]]:
    """R1 + R2 -- every agent whose newest marker is still a claim."""
    anonymous = ""
    for created, kind, fields in markers:
        if kind == "release" and not fields.get("agent"):
            anonymous = created
    latest: dict[str, tuple[str, str, dict[str, str]]] = {}
    for created, kind, fields in markers:
        if anonymous and created <= anonymous:
            continue
        latest[fields.get("agent", "")] = (created, kind, fields)
    return [(created, fields) for created, kind, fields in latest.values()
            if kind == "claim" and fields]


def _score(
    created: str, fields: dict[str, str], *, now: datetime, ttl_hours: int,
    branch_activity_for: Callable[[str], datetime | None] | None,
) -> dict[str, Any]:
    """R3 -- one holder's staleness, consulting its branch only if it may help."""
    last = _as_dt(fields.get("at", "")) or _as_dt(created[:19] + "Z")
    expired = last is None or (now - last) > timedelta(hours=ttl_hours)
    branch = fields.get("branch") or ""
    if expired and branch_activity_for and branch:
        activity = branch_activity_for(branch)
        if activity and (last is None or activity > last):
            last = activity
    stale = last is None or (now - last) > timedelta(hours=ttl_hours)
    return {**fields, "stale": stale,
            "age_hours": round((now - last).total_seconds() / 3600, 1) if last else None}


def active_claim(
    comments: list[dict[str, Any]], *, now: datetime, ttl_hours: int = CLAIM_TTL_HOURS,
    branch_activity_for: Callable[[str], datetime | None] | None = None,
) -> dict[str, Any] | None:
    """Who holds this issue, or None. R1-R4 above.

    ``branch_activity_for`` maps a branch to its last commit time. Only a
    caller can fetch that, so this stays pure (ADR 003); omit it and staleness
    falls back to claim age alone, which is what every path did before the
    branch became part of the answer.
    """
    scored: list[tuple[tuple[str, str], dict[str, Any]]] = []
    for created, fields in _surviving(_markers(comments)):
        claim = _score(created, fields, now=now, ttl_hours=ttl_hours,
                       branch_activity_for=branch_activity_for)
        scored.append(((fields.get("at", ""), created), claim))
    if not scored:
        return None
    live = [row for row in scored if not row[1]["stale"]]
    return min(live or scored, key=lambda row: row[0])[1]


def claim_for(
    comments: list[dict[str, Any]], *, agent: str, batch: str | None = None,
) -> dict[str, str] | None:
    """R5 -- the surviving claim belonging to ``agent``, never the elected one.

    `cmd_release` needs the branch IT claimed. With two surviving holders the
    elected claim belongs to the other agent, and cleaning up that branch
    deletes the ref a live claim points at. Fails closed: no match, no answer,
    so a mismatched agent id cleans up nothing rather than something.
    """
    for _created, fields in _surviving(_markers(comments)):
        if fields.get("agent") != agent:
            continue
        if batch is not None and fields.get("batch") != batch:
            continue
        return dict(fields)
    return None


def resolve_claim(
    comments: list[dict[str, Any]], *, now: datetime,
    branch_activity_for: Callable[[str], datetime | None] | None = None,
) -> dict[str, Any] | None:
    """The door every enforcement path uses, so `claims` and `next` agree."""
    return active_claim(comments, now=now, branch_activity_for=branch_activity_for)


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
