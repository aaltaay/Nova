"""Deterministic maintainability / danger checks for the Nova maintainer subagent.

Side-effect-free: reads the repo, prints a human report or JSON, exits 0 always
(unless --fail-on-findings / --fail-on-kind). The LLM triage layer decides
severity policy; this script only measures. ``--update-baselines`` is the one
write: it rewrites ``maintainer_lib/baselines.json`` to the tree.

Rules it measures: AGENTS.md §2 (ownership, size, feature imports), §6.3
(silent failures) and §6.7 (the backend lint, ruff). Architecture dependency
rules: architecture/dependency-rules.md.
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

from maintainer_lib import size_policy, swallow  # noqa: E402
from maintainer_lib.artifacts import check_artifacts as _check_artifacts  # noqa: E402
from maintainer_lib.baselines import (  # noqa: E402
    apply_baseline_counts,
    build_counts,
    load_counts,
    write_counts,
)
from maintainer_lib.deps import check_cross_feature_imports, check_import_main  # noqa: E402
from maintainer_lib.gate import GATE_KINDS  # noqa: E402
from maintainer_lib.ib_loop import check_ib_loop_purity as _check_ib_loop_purity  # noqa: E402
from maintainer_lib.lint import check_ruff  # noqa: E402
from maintainer_lib.owners import check_owners as _check_owners  # noqa: E402
from maintainer_lib.size_policy import count_lines  # noqa: E402,F401  (re-exported)
from maintainer_lib.sizes import LOGICAL_LIMIT_FILES, count_logical_lines  # noqa: E402

MAIN_PY_LIMIT = 200
APP_TSX_LIMIT = 150
INDEX_CSS_LIMIT = 50  # import-only barrel after Phase 2
SOFT_LIMIT = size_policy.SOFT_LIMIT
CEILING = size_policy.CEILING

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


def logical_line_counts(files: list[Path]) -> dict[str, int]:
    return {rel: count_logical_lines(path)
            for path in files if (rel := _rel(path)) in LOGICAL_LIMIT_FILES}


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


def _size_exempt(path: Path) -> bool:
    return _is_generated_path(path) or _is_test_path(path)


def check_file_sizes(files: list[Path], base: str | None = None) -> list[Finding]:
    """AGENTS.md §2.3. ``base`` (a resolved commit) turns on the growth check."""
    base_lines = None
    if base:
        def base_lines(rel: str) -> int | None:
            return size_policy.lines_at(REPO_ROOT, base, rel)
    return size_policy.check_file_sizes(
        files, _rel, Finding, HARD_LIMIT_FILES, _size_exempt, base_lines
    )


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
    """AGENTS.md §6.3; ``*_money`` kinds on the money path (maintainer_lib/swallow.py)."""
    # tools/ scripts and tests are deterministic one-offs, not the product
    # read paths this heuristic exists to protect.
    return swallow.check_swallowed_errors(
        files, _rel, Finding, lambda p: _is_tools_path(p) or _is_test_path(p)
    )


def check_owners() -> list[Finding]:
    return _check_owners(REPO_ROOT, Finding)


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


def check_ib_loop_purity(files: list[Path]) -> list[Finding]:
    return _check_ib_loop_purity(files, _rel, Finding)


def _collect(files: list[Path], base: str | None) -> list[Finding]:
    return (
        check_file_sizes(files, base)
        + check_secrets(files)
        + check_swallowed_errors(files)
        + check_artifacts()
        + check_import_main(files, _rel, Finding)
        + check_cross_feature_imports(files, _rel, Finding)
        + check_css_design_contract(files)
        + check_ib_loop_purity(files)
        + check_owners()
        + check_ruff(REPO_ROOT, Finding)
    )


def run_checks(base: str | None = None) -> dict:
    """``base`` is a ref (e.g. ``origin/master``); growth is judged against its
    merge-base with HEAD. Without it, growth is not judged."""
    files = iter_source_files()
    resolved = size_policy.resolve_base(REPO_ROOT, base)
    findings = _collect(files, resolved)
    if base and resolved is None:
        findings.append(Finding(
            kind="size_base_unavailable", path=".",
            detail=f"--base {base!r} has no merge-base with HEAD; file growth was not judged",
        ))
    for kind, key, allowed, actual in apply_baseline_counts(findings, load_counts()):
        findings.append(Finding(
            kind="baseline_stale", path="tools/maintainer_lib/baselines.json",
            detail=(f"{kind} {key}: frozen at {allowed}, tree has {actual} -- "
                    "lower it with --update-baselines"),
            baseline=True,
        ))
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
        "size_base": resolved,
        "css_line_counts": css_report,
        "logical_line_counts": logical_line_counts(files),
        "findings": [asdict(f) for f in findings],
    }


def update_baselines() -> dict[str, dict[str, int]]:
    """Rewrite baselines.json to the tree's current counts."""
    counts = build_counts(_collect(iter_source_files(), None))
    write_counts(counts)
    return counts


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
    parser.add_argument(
        "--fail-on-kind",
        action="append",
        default=[],
        help="Exit 1 if a non-baseline finding of this kind exists (repeatable)",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Exit 1 on any non-baseline finding of the CI gate kinds (maintainer_lib/gate.py)",
    )
    parser.add_argument(
        "--base",
        default="",
        help="Judge file growth against this ref's merge-base with HEAD (e.g. origin/master)",
    )
    parser.add_argument(
        "--update-baselines",
        action="store_true",
        help="Rewrite tools/maintainer_lib/baselines.json to the current tree and exit",
    )
    args = parser.parse_args(argv)
    if args.update_baselines:
        counts = update_baselines()
        total = sum(sum(rows.values()) for rows in counts.values())
        print(f"baselines.json: {total} frozen finding(s) across {len(counts)} kind(s)")
        return 0
    report = run_checks(args.base or None)
    if args.json:
        json.dump(report, sys.stdout, indent=2)
        print()
    else:
        print_human(report)
    if args.fail_on_findings and report["non_baseline_count"] > 0:
        return 1
    fail_kinds = set(args.fail_on_kind or []) | (set(GATE_KINDS) if args.gate else set())
    if fail_kinds:
        hits = [
            f
            for f in report["findings"]
            if (not f.get("baseline")) and f.get("kind") in fail_kinds
        ]
        if hits:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
