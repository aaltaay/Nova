"""Deterministic maintainability / danger checks for the Nova maintainer subagent.

Side-effect-free: reads the repo, prints a human report or JSON, exits 0 always
(unless --fail-on-findings). The LLM triage layer decides severity policy;
this script only measures.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Hard limits (mirrors .cursor/rules/file-size-limits.mdc)
MAIN_PY_LIMIT = 200
APP_TSX_LIMIT = 150
NEW_PY_LIMIT = 400
NEW_TSX_LIMIT = 300
NEW_TS_LIMIT = 400

# Documented known over-limit files — still reported with baseline=True
BASELINE_OVER_LIMIT: dict[str, int] = {
    "backend/hod_momo.py": 400,
    "backend/strategy/executor.py": 400,
}

HARD_LIMIT_FILES: dict[str, int] = {
    "backend/main.py": MAIN_PY_LIMIT,
    "frontend/src/App.tsx": APP_TSX_LIMIT,
}

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    "dist",
    ".cache",
    "__pycache__",
    ".venv",
    "venv",
    "graphify-out",
    "coverage",
    ".pytest_cache",
    "playwright-report",
    "test-results",
}

# High-signal secret-ish patterns (values are never printed — only the match kind)
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "generic_api_key_assign",
        re.compile(
            r"""(?i)(?:api[_-]?key|api[_-]?secret|secret[_-]?key|access[_-]?token)"""
            r"""\s*[=:]\s*['"][A-Za-z0-9_\-]{20,}['"]"""
        ),
    ),
    (
        "sk_live_or_test",
        re.compile(r"""(?i)['"]sk[_-](?:live|test)[_-][A-Za-z0-9]{16,}['"]"""),
    ),
]

SWALLOW_PY = re.compile(
    r"^[ \t]*except\s*(?:\w+(?:\s+as\s+\w+)?)?\s*:\s*(?:pass|\.\.\.)\s*(?:#.*)?$"
    r"|^[ \t]*except\s*(?:\w+(?:\s+as\s+\w+)?)?\s*:\s*\n[ \t]+(?:pass|\.\.\.)\s*(?:#.*)?$",
    re.MULTILINE,
)
BARE_EXCEPT_PY = re.compile(r"^[ \t]*except\s*:\s*", re.MULTILINE)
EMPTY_CATCH_JS = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}", re.MULTILINE)

ARTIFACT_PATHS = (
    "frontend/dist",
    "backend/.cache",
    ".env",
)


@dataclass
class Finding:
    kind: str
    path: str
    detail: str
    line: int | None = None
    baseline: bool = False


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def count_lines(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def iter_source_files() -> list[Path]:
    roots = [REPO_ROOT / "backend", REPO_ROOT / "frontend" / "src", REPO_ROOT / "tools"]
    out: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or _should_skip(path):
                continue
            if path.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx"}:
                out.append(path)
    return out


def _is_test_path(path: Path) -> bool:
    """Test suites are exempt from product file-size limits."""
    parts = {p.lower() for p in path.parts}
    name = path.name.lower()
    if "tests" in parts or "e2e" in parts:
        return True
    if name.startswith("test_") or name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
        return True
    return False


def check_file_sizes(files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        rel = _rel(path)
        if _is_test_path(path) and rel not in HARD_LIMIT_FILES and rel not in BASELINE_OVER_LIMIT:
            continue
        lines = count_lines(path)

        if rel in HARD_LIMIT_FILES:
            limit = HARD_LIMIT_FILES[rel]
            if lines > limit:
                findings.append(
                    Finding(
                        kind="file_size_hard",
                        path=rel,
                        detail=f"{lines} lines > hard limit {limit}",
                        baseline=False,
                    )
                )
            continue

        if rel in BASELINE_OVER_LIMIT:
            limit = BASELINE_OVER_LIMIT[rel]
            if lines > limit:
                findings.append(
                    Finding(
                        kind="file_size_baseline",
                        path=rel,
                        detail=f"{lines} lines > limit {limit} (accepted baseline)",
                        baseline=True,
                    )
                )
            continue

        if path.suffix == ".py" and lines > NEW_PY_LIMIT:
            findings.append(
                Finding(
                    kind="file_size",
                    path=rel,
                    detail=f"{lines} lines > Python module limit {NEW_PY_LIMIT}",
                )
            )
        elif path.suffix == ".tsx" and lines > NEW_TSX_LIMIT:
            findings.append(
                Finding(
                    kind="file_size",
                    path=rel,
                    detail=f"{lines} lines > React component limit {NEW_TSX_LIMIT}",
                )
            )
        elif path.suffix in {".ts", ".js", ".jsx"} and lines > NEW_TS_LIMIT:
            findings.append(
                Finding(
                    kind="file_size",
                    path=rel,
                    detail=f"{lines} lines > TypeScript limit {NEW_TS_LIMIT}",
                )
            )
    return findings


def check_secrets(files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        rel = _rel(path)
        if "test" in path.name.lower() or path.suffix in {".md"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for kind, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    Finding(
                        kind="secret_pattern",
                        path=rel,
                        detail=f"matched pattern '{kind}' (value redacted)",
                        line=line,
                    )
                )
    return findings


def check_swallowed_errors(files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        rel = _rel(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path.suffix == ".py":
            for match in SWALLOW_PY.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    Finding(
                        kind="swallowed_exception",
                        path=rel,
                        detail="except …: pass/… swallow",
                        line=line,
                    )
                )
            # Bare except that is not already counted as swallow-with-pass
            for match in BARE_EXCEPT_PY.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                snippet = text[match.start() : match.start() + 40]
                if "pass" in snippet or "..." in snippet:
                    continue
                findings.append(
                    Finding(
                        kind="bare_except",
                        path=rel,
                        detail="bare except:",
                        line=line,
                    )
                )
        elif path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
            for match in EMPTY_CATCH_JS.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    Finding(
                        kind="empty_catch",
                        path=rel,
                        detail="empty catch { }",
                        line=line,
                    )
                )
    return findings


def check_artifacts() -> list[Finding]:
    findings: list[Finding] = []
    for rel in ARTIFACT_PATHS:
        path = REPO_ROOT / rel
        if path.exists():
            findings.append(
                Finding(
                    kind="artifact_present",
                    path=rel,
                    detail="local/generated path exists — ensure it is gitignored and not staged",
                )
            )
    return findings


def run_checks() -> dict:
    files = iter_source_files()
    findings = (
        check_file_sizes(files)
        + check_secrets(files)
        + check_swallowed_errors(files)
        + check_artifacts()
    )
    non_baseline = [f for f in findings if not f.baseline]
    return {
        "repo_root": str(REPO_ROOT),
        "files_scanned": len(files),
        "finding_count": len(findings),
        "non_baseline_count": len(non_baseline),
        "findings": [asdict(f) for f in findings],
    }


def print_human(report: dict) -> None:
    print(f"Maintainer checks — scanned {report['files_scanned']} files")
    print(
        f"Findings: {report['finding_count']} "
        f"({report['non_baseline_count']} non-baseline)"
    )
    print()
    if not report["findings"]:
        print("No findings.")
        return
    for raw in report["findings"]:
        tag = "BASELINE" if raw["baseline"] else raw["kind"].upper()
        loc = f"{raw['path']}"
        if raw["line"] is not None:
            loc = f"{loc}:{raw['line']}"
        print(f"[{tag}] {loc} — {raw['detail']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit 1 if any non-baseline finding exists",
    )
    args = parser.parse_args(argv)
    report = run_checks()
    if args.json:
        json.dump(report, sys.stdout, indent=2)
        print()
    else:
        print_human(report)
    if args.fail_on_findings and report["non_baseline_count"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
