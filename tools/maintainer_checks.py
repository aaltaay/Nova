"""Deterministic maintainability / danger checks for the Nova maintainer subagent.

Side-effect-free: reads the repo, prints a human report or JSON, exits 0 always
(unless --fail-on-findings). The LLM triage layer decides severity policy;
this script only measures.

Architecture dependency rules: architecture/dependency-rules.md (ADR track).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_DIR = str(REPO_ROOT / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from maintainer_lib.artifacts import ARTIFACT_PATHS, check_artifacts as _check_artifacts  # noqa: E402
from maintainer_lib.baselines import apply_baseline_fingerprints  # noqa: E402
from maintainer_lib.deps import check_cross_feature_imports, check_import_main  # noqa: E402

MAIN_PY_LIMIT = 200
APP_TSX_LIMIT = 150
NEW_PY_LIMIT = 400
NEW_TSX_LIMIT = 300
NEW_TS_LIMIT = 400
INDEX_CSS_LIMIT = 50  # import-only barrel after Phase 2
DOMAIN_CSS_LIMIT = 1000

# Limit for "over size" reporting; accepted_lines tracks growth (Phase 0 baseline).
# executor.py is under the hard 400-line limit again — keep dicts empty until a
# new deliberate oversize baseline is accepted (see file-size-limits.mdc).
BASELINE_OVER_LIMIT: dict[str, int] = {}
BASELINE_ACCEPTED_LINES: dict[str, int] = {}

HARD_LIMIT_FILES: dict[str, int] = {
    "backend/main.py": MAIN_PY_LIMIT,
    "frontend/src/App.tsx": APP_TSX_LIMIT,
    "frontend/src/index.css": INDEX_CSS_LIMIT,
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

# Single-name, bare, and tuple handlers that only pass / ...
# e.g. `except Exception: pass`, `except (A, B):\n    pass`
SWALLOW_PY = re.compile(
    r"^[ \t]*except\s*(?:\([^)]+\)|\w+(?:\s+as\s+\w+)?)?\s*:\s*(?:pass|\.\.\.)\s*(?:#.*)?$"
    r"|^[ \t]*except\s*(?:\([^)]+\)|\w+(?:\s+as\s+\w+)?)?\s*:\s*\n[ \t]+(?:pass|\.\.\.)\s*(?:#.*)?$",
    re.MULTILINE,
)
BARE_EXCEPT_PY = re.compile(r"^[ \t]*except\s*:\s*", re.MULTILINE)
EMPTY_CATCH_JS = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}", re.MULTILINE)
# Promise .catch(() => {}) / .catch(() => {/* silent */})
EMPTY_CATCH_PROMISE_JS = re.compile(
    r"\.catch\(\s*\([^)]*\)\s*=>\s*\{\s*(?:/\*[^*]*\*/\s*)?\}\s*\)",
    re.MULTILINE,
)
# except …: return [] / {}  (failure disguised as empty market / empty state)
EXCEPT_RETURN_EMPTY_PY = re.compile(
    r"^[ \t]*except\b[^\n]*:\s*(?:#.*)?\n"
    r"(?:[ \t]+(?:logger\.[a-z_]+\([^\n]*\)|#[^\n]*)\n)*"
    r"[ \t]+return\s+(\[\s*\]|\{\s*\})\s*(?:#.*)?$",
    re.MULTILINE,
)

# Policy (bucket B, fail-loud remainder plan): swallow heuristics target
# unlogged product-code silence — not tools/tests, and not paths where an
# empty/disk-load failure is already deliberate and logged. See
# docs/agent-operations.md "Swallow heuristic policy" for the one-paragraph
# rationale. Do not add entries here for read paths that can silently
# disguise a real market/account failure as empty success (e.g. scanner
# discovery, IBKR positions/orders) — those must raise or log loudly instead.
EXCEPT_RETURN_EMPTY_ALLOWLIST = {
    "backend/cache.py",  # corrupt disk cache -> empty, already logged
    "backend/alerts/channels_store.py",  # corrupt channels config -> empty, already logged
    "backend/journal/tags.py",  # bad tag JSON -> no tags (non-trading, cosmetic)
    "backend/ibkr/client.py",  # managedAccounts() failure -> [] then paper-pin refuses (fail-closed)
    "backend/scanner.py",  # Alpaca snapshot/news chunk failures — already loud-logged degrades
}

# except: pass sites already triaged as intentional (idempotent cleanup /
# parse-then-try-next-format) rather than a silently swallowed failure.
SWALLOWED_EXCEPTION_ALLOWLIST = {
    "backend/ibkr/ticks.py",  # idempotent listener/list.remove + skip a malformed tick field
    "backend/ibkr/order_times.py",  # ISO parse fails -> fall through to next known format
}

SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".css"}

# Feature/domain CSS must not use bare element selectors (ADR 006).
BARE_FEATURE_SELECTOR = re.compile(
    r"^(form|label|input(?!\[)|button|table|thead|tbody|th|td|header)\s*[,{]",
    re.MULTILINE,
)
# Domain CSS must not read Tailwind --color-muted as text (collision with bg token).
COLOR_MUTED_AS_TEXT = re.compile(r"color\s*:\s*var\(\s*--color-muted\b")
# Allowed adapter / token sheets for Tailwind semantic vars.
CSS_TOKEN_ADAPTER_PATHS = {
    "frontend/src/styles/tailwind-theme.css",
    "frontend/src/index.css",
}


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
            if path.suffix.lower() in SOURCE_SUFFIXES:
                out.append(path)
    return out


def _is_test_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    name = path.name.lower()
    if "tests" in parts or "e2e" in parts:
        return True
    if name.startswith("test_") or name.endswith(
        (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")
    ):
        return True
    return False


def _is_generated_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    return bool(parts & {"dist", "coverage", "graphify-out", ".cache"})


def check_file_sizes(files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        rel = _rel(path)
        if _is_generated_path(path):
            continue
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
            accepted = BASELINE_ACCEPTED_LINES.get(rel, limit)
            if lines > accepted:
                findings.append(
                    Finding(
                        kind="baseline_growth",
                        path=rel,
                        detail=f"{lines} lines > accepted baseline {accepted}",
                        baseline=False,
                    )
                )
            elif lines > limit:
                findings.append(
                    Finding(
                        kind="file_size_baseline",
                        path=rel,
                        detail=f"{lines} lines > limit {limit} (accepted baseline <={accepted})",
                        baseline=True,
                    )
                )
            continue

        if path.suffix == ".css" and lines > DOMAIN_CSS_LIMIT:
            findings.append(
                Finding(
                    kind="file_size",
                    path=rel,
                    detail=f"{lines} lines > CSS stylesheet limit {DOMAIN_CSS_LIMIT}",
                )
            )
        elif path.suffix == ".py" and lines > NEW_PY_LIMIT:
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
        if path.suffix == ".css" or "test" in path.name.lower():
            continue
        rel = _rel(path)
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


def _is_tools_path(path: Path) -> bool:
    return "tools" in {p.lower() for p in path.parts}


def check_swallowed_errors(files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if path.suffix == ".css":
            continue
        rel = _rel(path)
        rel_posix = rel.replace("\\", "/")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path.suffix == ".py":
            # tools/ scripts and tests are deterministic/idempotent one-offs,
            # not the product read-paths this heuristic exists to protect
            # (see EXCEPT_RETURN_EMPTY_ALLOWLIST docstring policy note).
            skip_py_swallow_checks = _is_tools_path(path) or _is_test_path(path)
            if not skip_py_swallow_checks:
                for match in SWALLOW_PY.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    if rel_posix in SWALLOWED_EXCEPTION_ALLOWLIST:
                        continue
                    findings.append(
                        Finding(
                            kind="swallowed_exception",
                            path=rel,
                            detail="except …: pass/… swallow",
                            line=line,
                        )
                    )
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
                for match in EXCEPT_RETURN_EMPTY_PY.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    if rel_posix in EXCEPT_RETURN_EMPTY_ALLOWLIST:
                        continue
                    findings.append(
                        Finding(
                            kind="except_return_empty",
                            path=rel,
                            detail=f"except …: return {match.group(1)} — failure may look like empty market",
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
            for match in EMPTY_CATCH_PROMISE_JS.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    Finding(
                        kind="empty_promise_catch",
                        path=rel,
                        detail="empty .catch(() => {})",
                        line=line,
                    )
                )
    return findings


def check_artifacts() -> list[Finding]:
    return _check_artifacts(REPO_ROOT, Finding)


def check_css_design_contract(files: list[Path]) -> list[Finding]:
    """Reject bare feature selectors and --color-muted used as text (ADR 006)."""
    findings: list[Finding] = []
    for path in files:
        if path.suffix != ".css":
            continue
        rel = _rel(path)
        if _is_generated_path(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if rel not in CSS_TOKEN_ADAPTER_PATHS:
            for match in BARE_FEATURE_SELECTOR.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    Finding(
                        kind="bare_css_selector",
                        path=rel,
                        detail=f"bare '{match.group(1)}' selector — scope to a feature class (ADR 006)",
                        line=line,
                    )
                )
            for match in COLOR_MUTED_AS_TEXT.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    Finding(
                        kind="css_token_collision",
                        path=rel,
                        detail="color: var(--color-muted) — use --nova-text-muted / --text-secondary (ADR 006)",
                        line=line,
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
        + check_import_main(files, _rel, Finding)
        + check_cross_feature_imports(files, _rel, Finding)
        + check_css_design_contract(files)
    )
    apply_baseline_fingerprints(findings)
    non_baseline = [f for f in findings if not f.baseline]
    css_report = {
        _rel(p): count_lines(p)
        for p in files
        if p.suffix == ".css" and not _is_generated_path(p)
    }
    return {
        "repo_root": str(REPO_ROOT),
        "files_scanned": len(files),
        "finding_count": len(findings),
        "non_baseline_count": len(non_baseline),
        "css_line_counts": css_report,
        "findings": [asdict(f) for f in findings],
    }


def print_human(report: dict) -> None:
    print(f"Maintainer checks - scanned {report['files_scanned']} files")
    print(
        f"Findings: {report['finding_count']} "
        f"({report['non_baseline_count']} non-baseline)"
    )
    css = report.get("css_line_counts") or {}
    if css:
        print("CSS stylesheets:")
        for path, lines in sorted(css.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {lines:5d}  {path}")
    print()
    if not report["findings"]:
        print("No findings.")
        return
    for raw in report["findings"]:
        tag = "BASELINE" if raw["baseline"] else raw["kind"].upper()
        loc = f"{raw['path']}"
        if raw["line"] is not None:
            loc = f"{loc}:{raw['line']}"
        print(f"[{tag}] {loc} - {raw['detail']}")


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
