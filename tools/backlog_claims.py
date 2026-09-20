"""Cross-tool advisory claims on a backlog PR batch.

Agents run from several tools (Claude Code, Codex, Cursor) and all of them
authenticate as the same GitHub account, so `assignee` cannot say WHO holds a
piece of work. GitHub is the only substrate every tool can see, so the claim
lives there: a `claimed` label for cheap filtering plus a structured comment
carrying agent id, branch and timestamp.

The lock unit is the PR BATCH, not the issue -- the batch is already the unit
of work, so locking per-issue would create four locks for one job.

This is ADVISORY. Two agents can both read "unclaimed" before either writes;
GitHub offers no compare-and-swap on labels. The `claim` command therefore
re-reads after writing and yields if an earlier live claim exists (earliest
`at` wins), which makes a collision detectable and resolvable rather than
impossible. An agent that ignores the protocol will still collide."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

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
