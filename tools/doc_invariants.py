"""Fail CI when live docs re-introduce known-stale present-tense claims.

Scans constitution, README, env examples, rules, docs/, security markdown,
and a few generator strings. Historical CHANGELOG / PROBLEM_LOG / task-log
are excluded on purpose -- archives may narrate past Railway/Alpaca eras.

Usage:
  py -3 tools/doc_invariants.py
  py -3 tools/doc_invariants.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Relative paths and globs under REPO_ROOT (forward slashes).
LIVE_PATHS: tuple[str, ...] = (
    "AGENTS.md",
    "README.md",
    "findings.md",
    ".env.example",
    "frontend/.env.example",
    ".github/workflows/deploy.yml",
    "docs/agent-operations.md",
    "docs/shadow-day-log-template.md",
    "security/tooling.md",
    "security/schema.md",
    "security/SOURCE-PINS.md",
    "SECURITY.md",
    "site/index.html",
    "tools/security_lib/checks_api.py",
    "tools/security_lib/checks_infra.py",
)

LIVE_GLOBS: tuple[str, ...] = (
    ".cursor/rules/*.mdc",
)

# (id, compiled pattern, human reason)
INVARIANTS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "railway_deployed",
        re.compile(r"(?i)deployed to Railway"),
        "Claims API/backend is deployed to Railway (backend is local-only).",
    ),
    (
        "railway_deploy_job",
        re.compile(r"(?i)Deploy to Railway"),
        "Mentions a Railway deploy job (CI must not ship a cloud backend).",
    ),
    (
        "railway_auto_deploy",
        re.compile(r"(?i)auto-deploys?\s+from\b.*\bRailway"),
        "Claims git auto-deploys the backend to Railway.",
    ),
    (
        "railway_cloud_row",
        re.compile(r"(?i)\|\s*Railway\s*\|\s*Cloud deployment"),
        "Integrations table still lists Railway as cloud deployment.",
    ),
    (
        "no_architecture_dir",
        re.compile(r"(?i)No `architecture/` directory exists"),
        "Claims architecture/ is missing (ADRs exist under architecture/).",
    ),
    (
        "no_automated_tests",
        re.compile(r"(?i)No automated tests exist"),
        "Claims no automated tests exist (pytest + Vitest suites exist).",
    ),
    (
        "absolute_no_trades",
        re.compile(
            r"(?i)does not execute(?: or manipulate)? trades"
        ),
        "Absolute no-trades claim conflicts with gated IBKR execution (Invariant #7).",
    ),
    (
        "alpaca_market_sot",
        re.compile(
            r"(?i)Source of Truth\s*\([^)]*\)\s*\|\s*Alpaca Market Data"
        ),
        "Names Alpaca as primary market-data SoT (IBKR is the price/scanner feed).",
    ),
    (
        "alpaca_required_scanner",
        re.compile(r"(?i)Alpaca credentials\s*\([^)]*required for Nova scanner"),
        ".env.example must not say Alpaca is required for the scanner.",
    ),
    (
        "discovery_alpaca_mode",
        re.compile(r"(?i)(?:use\s+)?discovery\s*=\s*alpaca"),
        "Instructs discovery=alpaca (product coerces to ibkr; not a real mode).",
    ),
    (
        "phase_b_is_next",
        re.compile(r"(?i)while Phase B is NEXT"),
        "Scope guard still treats Phase B as NEXT (B is waived; see Roadmap Status).",
    ),
    (
        "do_not_promote_k_z",
        re.compile(r"(?i)Do not promote Phases K[–-]Z"),
        "Blocks promoting K–Z while K is the active product phase (parking lot is L–Z).",
    ),
    (
        "nova_public_as_source",
        re.compile(r"github\.com/aaltaay/Nova-public"),
        "Live docs still treat Nova-public as the public source (aaltaay/Nova is the source home).",
    ),
)


@dataclass(frozen=True)
class Violation:
    invariant_id: str
    path: str
    line: int
    snippet: str
    reason: str


def _iter_live_files(root: Path) -> list[Path]:
    found: set[Path] = set()
    for rel in LIVE_PATHS:
        path = root / rel
        if path.is_file():
            found.add(path.resolve())
    for pattern in LIVE_GLOBS:
        for path in root.glob(pattern):
            if path.is_file():
                found.add(path.resolve())
    return sorted(found)


def scan_text(path: Path, text: str) -> list[Violation]:
    rel = path.as_posix()
    try:
        rel = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        pass
    hits: list[Violation] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for inv_id, pattern, reason in INVARIANTS:
            if pattern.search(line):
                hits.append(
                    Violation(
                        invariant_id=inv_id,
                        path=rel,
                        line=line_no,
                        snippet=line.strip()[:200],
                        reason=reason,
                    )
                )
    return hits


def run_scan(root: Path | None = None) -> list[Violation]:
    base = root or REPO_ROOT
    violations: list[Violation] = []
    for path in _iter_live_files(base):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            violations.append(
                Violation(
                    invariant_id="read_error",
                    path=str(path),
                    line=0,
                    snippet=str(exc),
                    reason="Could not read live doc path.",
                )
            )
            continue
        violations.extend(scan_text(path, text))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit violations as JSON on stdout.",
    )
    args = parser.parse_args(argv)
    violations = run_scan()
    if args.json:
        print(json.dumps([asdict(v) for v in violations], indent=2))
    elif not violations:
        print("doc_invariants: OK (no stale live-doc claims)")
    else:
        print(f"doc_invariants: {len(violations)} violation(s)", file=sys.stderr)
        for v in violations:
            print(
                f"  [{v.invariant_id}] {v.path}:{v.line}: {v.snippet}",
                file=sys.stderr,
            )
            print(f"    -> {v.reason}", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
