"""HOD Momo + scanner integrity evaluators — fail loud on invisible data bugs.

Strangler facade (ADR 004). Implementation lives in:
  hod_momo_integrity_common, hod_momo_integrity_hod, hod_momo_integrity_scanner.

Used by:
  - GET /api/hod-momo/debug/integrity
  - GET /api/scan/integrity
  - GET /api/integrity
  - tools/hod_momo_integrity_check.py
  - background integrity_loop (loud WARN logs)

Statuses: pass | warn | fail. Overall = worst check.

Facade owner: Phase 10 / Pattern-Driven Architecture.
Removal criterion: no production caller imports this facade instead of
``hod_momo_integrity_hod`` / ``hod_momo_integrity_scanner`` directly.
"""
from __future__ import annotations

from typing import Any

from hod_momo_integrity_common import worst
from hod_momo_integrity_hod import evaluate_hod_integrity
from hod_momo_integrity_scanner import evaluate_scanner_integrity

__all__ = [
    "evaluate_hod_integrity",
    "evaluate_scanner_integrity",
    "merge_integrity",
]


def merge_integrity(*reports: dict[str, Any]) -> dict[str, Any]:
    """Combine HOD + scanner reports into one overall verdict."""
    checks: list[dict[str, str]] = []
    for r in reports:
        checks.extend(list(r.get("checks") or []))
    status = worst([c["status"] for c in checks]) if checks else "pass"
    return {
        "ok": status == "pass",
        "status": status,
        "scope": "all",
        "checks": checks,
        "parts": {r.get("scope", "?"): r.get("status") for r in reports},
    }
