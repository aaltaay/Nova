"""Fail CI when live docs re-introduce known-stale present-tense claims.

Scans constitution, README, env examples, rules, docs/, security markdown,
and a few generator strings. Historical CHANGELOG / archived ledgers / task-log
prose is excluded on purpose -- archives may narrate past Railway/Alpaca eras.
CHANGELOG is checked for *structure* only (one standalone
entries marker, no entry above it, title on line 1), because an entry written
against the marker's prose mention corrupts the instructions themselves.

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


# Agent-maintained entry logs: (path, expected H1).
#
# Both files quote their own insert anchor in prose ("immediately below the
# `<!-- ENTRIES_START -->` marker"), so the FIRST textual match of the marker is
# that sentence, ~50 lines above the real standalone marker line. Four commits
# (bd0d0cb6, e4a73ef9, 5854569, 58f6bc7) prepended by first match and buried
# their entry inside the how-to block, splitting the instruction mid-sentence.
# These checks are structural only -- entry prose is never scanned for stale
# claims, per the module docstring.
ENTRY_LOGS: tuple[tuple[str, str], ...] = (
    ("CHANGELOG.md", "# Change log (agent-maintained)"),
)

ENTRIES_MARKER = "<!-- ENTRIES_START -->"

# Headings allowed above the marker: the how-to section and the entry template.
ENTRY_LOG_ALLOWED_HEADINGS: tuple[str, ...] = (
    "## How agents update this file",
    "## YYYY-MM-DD",
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


def missing_live_paths(root: Path) -> list[str]:
    """Declared LIVE_PATHS entries that do not resolve to a file.

    A renamed or deleted live doc would otherwise drop out of the scan set
    silently and the gate would keep exiting 0 on shrinking coverage.
    LIVE_GLOBS is exempt: a glob may legitimately match nothing.
    """
    return [rel for rel in LIVE_PATHS if not (root / rel).is_file()]


def check_entry_log(rel: str, title: str, text: str) -> list[Violation]:
    """Structural checks for one agent-maintained entry log.

    Catches the first-match prepend: an entry written under the prose mention
    of the marker instead of under the standalone marker line. Absent files are
    the caller's concern; this only inspects content it was handed.
    """
    lines = text.split("\n")
    hits: list[Violation] = []

    def add(inv_id: str, line: int, snippet: str, reason: str) -> None:
        hits.append(
            Violation(
                invariant_id=inv_id,
                path=rel,
                line=line,
                snippet=snippet.strip()[:200],
                reason=reason,
            )
        )

    if not lines or lines[0] != title:
        add(
            "entry_log_title",
            1,
            lines[0] if lines else "",
            f"{rel} must start with its H1 ({title!r}). Content above the title "
            "means an entry was prepended to the file instead of to the entries "
            "section.",
        )

    marker_lines = [i for i, ln in enumerate(lines, start=1) if ln == ENTRIES_MARKER]
    if len(marker_lines) != 1:
        add(
            "entry_log_marker",
            marker_lines[0] if marker_lines else 0,
            f"found {len(marker_lines)} standalone {ENTRIES_MARKER} lines",
            f"{rel} needs exactly one line equal to {ENTRIES_MARKER}; entries go "
            "below it. Zero or several means the anchor is ambiguous and the next "
            "prepend will land somewhere unpredictable.",
        )
        return hits

    marker_at = marker_lines[0]
    for i, line in enumerate(lines[: marker_at - 1], start=1):
        if line.startswith("## ") and not line.startswith(ENTRY_LOG_ALLOWED_HEADINGS):
            add(
                "entry_log_entry_above_marker",
                i,
                line,
                f"{rel} has a '##' entry heading above the {ENTRIES_MARKER} line "
                f"(marker is line {marker_at}). Entries belong below the marker; "
                "this one was almost certainly anchored on the marker's prose "
                "mention instead of the marker line.",
            )
        if ENTRIES_MARKER in line and line.rstrip().endswith(ENTRIES_MARKER):
            add(
                "entry_log_howto_split",
                i,
                line,
                f"{rel} how-to line ends with {ENTRIES_MARKER}, so its sentence "
                "was cut off by text appended after the marker mention. Restore "
                "the full sentence and move the appended content below the marker.",
            )
    return hits


def check_entry_logs(root: Path) -> list[Violation]:
    """Run entry-log structure checks for every ENTRY_LOGS file present."""
    violations: list[Violation] = []
    for rel, title in ENTRY_LOGS:
        path = root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            violations.append(
                Violation(
                    invariant_id="read_error",
                    path=rel,
                    line=0,
                    snippet=str(exc),
                    reason="Could not read agent-maintained entry log.",
                )
            )
            continue
        violations.extend(check_entry_log(rel, title, text))
    return violations


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
    for rel in missing_live_paths(base):
        violations.append(
            Violation(
                invariant_id="missing_live_path",
                path=rel,
                line=0,
                snippet="declared in LIVE_PATHS but not found on disk",
                reason=(
                    "A declared live doc is missing, so the gate stopped checking it. "
                    "Restore the file or update LIVE_PATHS deliberately."
                ),
            )
        )
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
    violations.extend(check_entry_logs(base))
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
        print("doc_invariants: OK (live-doc claims + entry-log structure)")
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
