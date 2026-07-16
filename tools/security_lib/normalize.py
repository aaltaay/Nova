"""Finding normalization: fingerprinting and SEC-NNN ID assignment.

Side-effect-free: no I/O.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, timezone, datetime
from typing import Any


def fingerprint(source: str, kind: str, path: str, title: str) -> str:
    """Stable SHA-256 fingerprint for a finding.

    Inputs are lowercased and stripped so minor tool output variations do not
    produce different fingerprints for the same logical issue.
    """
    canonical = "\x00".join(
        [source.strip().lower(), kind.strip().lower(), path.strip(), title.strip()]
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def format_id(n: int) -> str:
    """Return SEC-NNN style ID (minimum 3 digits)."""
    return f"SEC-{n:03d}"


def today_iso() -> str:
    return date.today().isoformat()


@dataclass
class RawFinding:
    """Intermediate result produced by a scanner/check before registry merge."""

    source: str
    kind: str
    path: str
    title: str
    detail: str
    severity: str  # critical|high|medium|low
    location: str  # file:line
    redacted_evidence: str = ""
    cvss_vector: str = ""
    cvss_score: float | None = None
    cwe: str = ""
    asvs: str = ""

    @property
    def fp(self) -> str:
        return fingerprint(self.source, self.kind, self.path, self.title)


def raw_to_registry_entry(
    raw: RawFinding,
    sec_id: str,
    first_seen: str,
    last_seen: str,
) -> dict[str, Any]:
    """Convert a RawFinding into a registry finding dict (new entry)."""
    entry: dict[str, Any] = {
        "id": sec_id,
        "fingerprint": raw.fp,
        "status": "open",
        "severity": raw.severity,
        "title": raw.title,
        "detail": raw.detail,
        "location": raw.location,
        "source": raw.source,
        "first_seen": first_seen,
        "last_seen": last_seen,
    }
    if raw.redacted_evidence:
        entry["redacted_evidence"] = raw.redacted_evidence
    if raw.cvss_vector:
        entry["cvss_vector"] = raw.cvss_vector
    if raw.cvss_score is not None:
        entry["cvss_score"] = raw.cvss_score
    if raw.cwe:
        entry["cwe"] = raw.cwe
    if raw.asvs:
        entry["asvs"] = raw.asvs
    # Fields set by human triage — empty at creation time
    entry["compensating_controls"] = ""
    entry["acceptance_rationale"] = ""
    entry["review_by"] = ""
    entry["evidence_commit"] = ""
    return entry
