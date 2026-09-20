"""Pure, authored file footprints for advisory backlog claims (#367).

Files match exactly; trailing-slash directories include descendants. No git
inspection or network calls: the plan and claim comments are the inputs.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

OVERLAP_REASON = "files overlap an in-flight claim"
UNKNOWN_FOOTPRINT = "footprint unavailable; review the live claim"


def normalize_touches(paths: Iterable[str]) -> list[str]:
    if isinstance(paths, (str, bytes)):
        raise ValueError("touches must be a list of repository paths")
    result = set()
    for raw in paths:
        if not isinstance(raw, str):
            raise ValueError("touches entries must be strings")
        path = raw.strip().replace("\\", "/").casefold()
        while path.startswith("./"):
            path = path[2:]
        parts = path.rstrip("/").split("/")
        if (not path or path.startswith("/") or any(p in ("", ".", "..") for p in parts)
                or any(c in path for c in ":*?[]\n\r")):
            raise ValueError(f"invalid repository footprint: {raw!r}")
        result.add(path)
    return sorted(result)


def batch_touches(pkg: dict[str, Any], batch: dict[str, Any]) -> list[str]:
    return normalize_touches(batch.get("touches", pkg.get("touches", [])))


def overlapping_paths(left: Iterable[str], right: Iterable[str]) -> list[str]:
    """Return the more specific overlapping path, once, in stable order."""
    hits = set()
    for a in normalize_touches(left):
        for b in normalize_touches(right):
            if a == b:
                hits.add(a)
            elif a.endswith("/") and b.startswith(a):
                hits.add(b)
            elif b.endswith("/") and a.startswith(b):
                hits.add(a)
    return sorted(hits)


def claim_touches(
    number: int, claim: dict[str, Any], packages: list[dict[str, Any]]
) -> list[str] | None:
    """Prefer the snapshot; resolve legacy comments by batch, then issue."""
    raw = claim.get("touches")
    if raw is not None:
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, list):
                paths = normalize_touches(parsed)
                if paths:
                    return paths
        except (ValueError, TypeError):
            pass  # A malformed snapshot falls back to the authored plan.
    slug, _, index = str(claim.get("batch", "")).rpartition("#")
    for pkg in packages:
        if pkg["slug"] == slug and index.isdigit() and int(index) < len(pkg.get("prs", [])):
            paths = batch_touches(pkg, pkg["prs"][int(index)])
            if paths:
                return paths
    paths = set()
    for pkg in packages:
        for batch in pkg.get("prs", []):
            if number in batch["issues"]:
                paths.update(batch_touches(pkg, batch))
    return sorted(paths) or None


def claim_conflicts(
    pkg: dict[str, Any], batch: dict[str, Any],
    claimed: Iterable[int] | Mapping[int, dict[str, Any]],
    packages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Live holders conflicting with this batch, deduplicated across issues.

Bare issue-number sets retain the old API (no claim metadata to inspect).
Unknown footprints block authored candidates rather than claiming safety.
"""
    mine = batch_touches(pkg, batch)
    if not mine or not isinstance(claimed, Mapping):
        return []
    conflicts: dict[tuple[str, str, str], dict[str, Any]] = {}
    for number, claim in sorted(claimed.items()):
        if claim.get("stale"):
            continue
        paths = claim_touches(number, claim, packages)
        overlap = overlapping_paths(mine, paths) if paths is not None else [UNKNOWN_FOOTPRINT]
        if not overlap:
            continue
        key = (claim.get("agent", "?"), claim.get("batch", "?"), claim.get("branch", "?"))
        row = conflicts.setdefault(key, {
            "agent": key[0], "batch": key[1], "branch": key[2],
            "issues": [], "paths": [], "at": claim.get("at", ""),
        })
        row["issues"].append(number)
        row["paths"] = sorted(set(row["paths"]) | set(overlap))
    return list(conflicts.values())


def live_issue_numbers(claimed: Iterable[int] | Mapping[int, dict[str, Any]]) -> set[int]:
    if isinstance(claimed, Mapping):
        return {n for n, c in claimed.items() if not c.get("stale")}
    return set(claimed)


def conflict_lines(conflicts: list[dict[str, Any]]) -> list[str]:
    return [
        f"{row['agent']} on {row['branch']} ({row['batch']}; "
        f"{', '.join('#%s' % n for n in row['issues'])}): {', '.join(row['paths'])}"
        for row in conflicts
    ]
