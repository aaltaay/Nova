"""Frozen counts for legacy architecture findings: a ratchet, not an allowlist.

``baselines.json`` holds, per kind, how many findings each ``path|detail`` may
carry. Up to that many are legacy (``baseline: true``); one more is new and
fails CI. Counts are keyed on path and detail, never on line numbers, so an
edit above an import does not break the baseline (the v1 line-number
fingerprints did). A count the tree no longer reaches is ``baseline_stale``:
lower it with ``--update-baselines``, which rewrites every count to the tree --
raising one is a decision the PR states.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

BASELINES_PATH = Path(__file__).resolve().parent / "baselines.json"
SCHEMA_VERSION = 2

# Kinds whose legacy instances may be frozen. Silent failures on the money path
# never are: those carry an allow-swallow reason at the site or get fixed.
BASELINE_KINDS = frozenset({"cross_feature_import", "import_main"})

_DESCRIPTION = (
    "Frozen counts of legacy findings per kind and 'path|detail'. A finding past "
    "its count is new and fails CI. Rewrite with "
    "`py -3 tools/maintainer_checks.py --update-baselines` and say why in the PR "
    "if a count goes up."
)


def _key(finding) -> str:
    return f"{getattr(finding, 'path', '')}|{getattr(finding, 'detail', '')}"


def load_counts(path: Path | None = None) -> dict[str, dict[str, int]]:
    """Frozen counts; empty when the file is absent. Unknown versions refuse."""
    p = path or BASELINES_PATH
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    version = data.get("schema_version")
    if version == 1:
        return {}  # v1 fingerprints were never populated; nothing to migrate
    if version != SCHEMA_VERSION:
        raise ValueError(f"{p}: unknown baselines schema_version {version!r}")
    counts = data.get("counts") or {}
    return {kind: {k: int(v) for k, v in (rows or {}).items()} for kind, rows in counts.items()}


def build_counts(findings: list) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(dict)
    for f in findings:
        kind = getattr(f, "kind", None)
        if kind in BASELINE_KINDS:
            rows = counts[kind]
            rows[_key(f)] = rows.get(_key(f), 0) + 1
    return {kind: dict(sorted(rows.items())) for kind, rows in sorted(counts.items())}


def write_counts(counts: dict[str, dict[str, int]], path: Path | None = None) -> None:
    payload = {"schema_version": SCHEMA_VERSION, "description": _DESCRIPTION, "counts": counts}
    (path or BASELINES_PATH).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def apply_baseline_counts(findings: list, counts: dict[str, dict[str, int]]) -> list[tuple]:
    """Mark legacy findings baseline; return ``(kind, key, allowed, actual)`` for stale counts."""
    seen: dict[tuple[str, str], int] = defaultdict(int)
    ordered = sorted(
        (f for f in findings if getattr(f, "kind", None) in BASELINE_KINDS),
        key=lambda f: (f.kind, _key(f), f.line or 0),
    )
    for f in ordered:
        slot = (f.kind, _key(f))
        seen[slot] += 1
        f.baseline = seen[slot] <= counts.get(f.kind, {}).get(_key(f), 0)
    stale = []
    for kind, rows in counts.items():
        for key, allowed in rows.items():
            actual = seen.get((kind, key), 0)
            if actual < allowed:
                stale.append((kind, key, allowed, actual))
    return stale
