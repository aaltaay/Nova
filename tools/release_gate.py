#!/usr/bin/env python3
"""Publish a vNNN Release only from a green build (operator decision 2026-10-13).

"Things should only be shipped with green builds." The desk's update feed
offers whatever GitHub Release is newest, so the Release is the shipment. The
Desktop pack run that packs a commit also calls the CI workflow on that same
commit, in full (its `verify` job, named ``Release checks``). Before the
installer becomes a Release, this gate reads that run's jobs and passes only
when the installer packed and every required check concluded ``success``.
Failed, cancelled, timed out, skipped, still running or missing all hold the
Release, and the gate says which check held it -- in the job summary and as an
error annotation -- so the operator can see why no update arrived.

The required checks are the verification jobs CI runs on every PR: the four
that were master's required status checks until the 2026-09-20 advisory-merge
decision. The security scanners stay warning-only, as their own workflow says.

Usage (the Desktop pack workflow's `Publish vNNN installer` job):
  gh api --paginate "repos/$REPO/actions/runs/$RUN_ID/jobs?filter=latest&per_page=100" > jobs.json
  python3 tools/release_gate.py --tag v812 --pack success --jobs-file jobs.json

Exit 0: publish. Exit 1: the Release is held (the reason is printed).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# The calling job in desktop-pack.yml: `name: Release checks`, id `verify`.
# GitHub lists a called workflow's jobs as "<caller> / <job name>"; either
# spelling of the caller is this run's verify call, and nothing else is.
CHECKS_PREFIX = "Release checks"
CALLER_NAMES: tuple[str, ...] = (CHECKS_PREFIX, "verify")
REQUIRED_CHECKS: tuple[str, ...] = (
    "Backend tests",
    "Frontend build",
    "Frontend E2E",
    "Agent contract",
)
PACK_CHECK = "Desktop pack"

_WORDS = {
    "failure": "failed",
    "cancelled": "was cancelled",
    "timed_out": "timed out",
    "skipped": "was skipped",
    "startup_failure": "failed to start",
    "action_required": "is waiting for approval",
    "neutral": "ended neutral",
    "stale": "went stale",
}


def _documents(text: str) -> list[Any]:
    """`gh api --paginate` prints one JSON document per page, back to back."""
    decoder = json.JSONDecoder()
    docs: list[Any] = []
    index = 0
    while True:
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            return docs
        doc, index = decoder.raw_decode(text, index)
        docs.append(doc)


def load_jobs(text: str) -> list[dict[str, Any]]:
    """Every job in the pages (or a `--slurp` array of pages, or a bare job list)."""
    jobs: list[dict[str, Any]] = []
    pending: list[Any] = list(_documents(text))
    while pending:
        doc = pending.pop(0)
        if isinstance(doc, list):
            pending[:0] = doc
        elif isinstance(doc, dict) and isinstance(doc.get("jobs"), list):
            jobs.extend(job for job in doc["jobs"] if isinstance(job, dict))
        elif isinstance(doc, dict) and "name" in doc:
            jobs.append(doc)
        else:
            raise ValueError("not a jobs listing")
    return jobs


def _recency(job: dict[str, Any]) -> tuple[int, int]:
    return int(job.get("run_attempt") or 0), int(job.get("id") or 0)


def _latest(jobs: list[dict[str, Any]], names: list[str]) -> dict[str, Any] | None:
    """The newest job under any of ``names``: its latest attempt, so a green re-run counts."""
    found = [job for job in jobs if str(job.get("name") or "") in names]
    return max(found, key=_recency, default=None)


def _state(result: str | None) -> str:
    result = (result or "").strip().lower()
    if not result:
        return "has no result"
    return _WORDS.get(result, result)


def verdict(
    jobs: list[dict[str, Any]],
    pack_result: str,
    *,
    callers: tuple[str, ...] = CALLER_NAMES,
    required: tuple[str, ...] = REQUIRED_CHECKS,
) -> list[tuple[str, str]]:
    """``(check, what happened)`` for everything that is not green; empty means publish."""
    held: list[tuple[str, str]] = []
    if (pack_result or "").strip().lower() != "success":
        held.append((PACK_CHECK, _state(pack_result)))
    for check in required:
        job = _latest(jobs, [f"{caller} / {check}" for caller in callers])
        if job is None:
            held.append((check, "did not run"))
        elif str(job.get("status") or "").lower() != "completed":
            held.append((check, f"is still {job.get('status') or 'pending'}"))
        elif str(job.get("conclusion") or "").lower() != "success":
            held.append((check, _state(job.get("conclusion"))))
    return held


def headline(tag: str, held: list[tuple[str, str]]) -> str:
    if not held:
        return f"{tag}: the installer packed and every release check is green -- publishing."
    return f"{tag} not published: " + "; ".join(f"{check} {state}" for check, state in held)


def summary(tag: str, held: list[tuple[str, str]], required: tuple[str, ...] = REQUIRED_CHECKS) -> str:
    lines = [f"### {headline(tag, held)}", ""]
    if held:
        lines += [
            "The desk's update feed only ever offers a Release built from a green commit "
            "(operator decision 2026-10-13), so this commit's installer was not published.",
            "",
            "| Check | Result |",
            "|---|---|",
            *(f"| {check} | {state} |" for check, state in held),
            "",
            f"A green re-run publishes {tag}: **Re-run failed jobs** on this run, or "
            f"`gh workflow run desktop-pack.yml --ref {tag}`.",
        ]
    else:
        lines.append("Green: " + ", ".join((PACK_CHECK, *required)) + ".")
    return "\n".join(lines) + "\n"


def _escape_annotation(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tag", required=True, help="the vNNN this run would publish")
    parser.add_argument("--pack", required=True, help="needs.desktop-pack.result")
    parser.add_argument("--jobs-file", required=True, type=Path,
                        help="this run's jobs, as `gh api --paginate` printed them")
    args = parser.parse_args(argv)

    try:
        jobs = load_jobs(args.jobs_file.read_text(encoding="utf-8"))
        held = verdict(jobs, args.pack)
    except (OSError, ValueError) as exc:
        # Fail closed: a gate that cannot see the checks never calls them green.
        held = [(CHECKS_PREFIX, f"could not be read ({exc})")]
        if (args.pack or "").strip().lower() != "success":
            held.insert(0, (PACK_CHECK, _state(args.pack)))

    text = summary(args.tag, held)
    print(text)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write(text)
    if held:
        print(f"::error title={args.tag} not published::{_escape_annotation(headline(args.tag, held))}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
