"""Committed fingerprint baselines for architecture findings."""

from __future__ import annotations

import json
from pathlib import Path

BASELINES_PATH = Path(__file__).resolve().parent / "baselines.json"

# Finding kinds whose legacy instances may be baselined via fingerprint.
FINGERPRINT_KINDS = frozenset(
    {
        "import_main",
        "cross_feature_import",
        "swallowed_exception",
        "bare_except",
        "empty_catch",
    }
)


def fingerprint(kind: str, path: str, line: int | None, detail: str) -> str:
    line_s = "" if line is None else str(line)
    return f"{kind}|{path}|{line_s}|{detail}"


def load_baseline_fingerprints(path: Path | None = None) -> set[str]:
    p = path or BASELINES_PATH
    if not p.is_file():
        return set()
    data = json.loads(p.read_text(encoding="utf-8"))
    return set(data.get("fingerprints") or [])


def apply_baseline_fingerprints(
    findings: list,
    fingerprints: set[str] | None = None,
) -> list:
    """Mark fingerprint-kind findings as baseline iff listed; else non-baseline."""
    fps = fingerprints if fingerprints is not None else load_baseline_fingerprints()
    for f in findings:
        kind = getattr(f, "kind", None)
        if kind not in FINGERPRINT_KINDS:
            continue
        fp = fingerprint(
            kind,
            getattr(f, "path", ""),
            getattr(f, "line", None),
            getattr(f, "detail", ""),
        )
        f.baseline = fp in fps
    return findings
