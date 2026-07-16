"""Architecture dependency checks (warning-first for legacy trees)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

FindingFactory = Callable[..., object]

IMPORT_MAIN_RE = re.compile(
    r"^[ \t]*(?:import\s+main(?:\s+as\s+\w+)?|from\s+main\s+import\s+.+)\s*(?:#.*)?$",
    re.MULTILINE,
)

# Feature slice roots under frontend/src (ADR 005)
FRONTEND_FEATURES = (
    "hod_momo",
    "hotkeys",
    "chart",
    "ibkr",
    "workspace",
    "modules",
    "reports",
    "backtest",
    "alerts",
)

CROSS_FEATURE_RE = re.compile(
    r"""(?:from|import)\s+['"](?:\.\./)+("""
    + "|".join(FRONTEND_FEATURES)
    + r""")/""",
)


def _is_test(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    name = path.name.lower()
    if "tests" in parts or "e2e" in parts:
        return True
    return name.startswith("test_") or name.endswith(
        (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")
    )


def check_import_main(
    files: list[Path],
    rel_fn: Callable[[Path], str],
    finding_cls: type,
) -> list:
    """Flag production lazy `import main` state access (tests exempt)."""
    findings = []
    for path in files:
        if path.suffix != ".py" or _is_test(path):
            continue
        rel = rel_fn(path)
        if rel in {"backend/main.py", "backend/run_api.py"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in IMPORT_MAIN_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                finding_cls(
                    kind="import_main",
                    path=rel,
                    detail="production import of main (use explicit state owner)",
                    line=line,
                    baseline=False,  # fingerprint baselines applied in run_checks
                )
            )
    return findings


def _feature_of(rel: str) -> str | None:
    prefix = "frontend/src/"
    if not rel.startswith(prefix):
        return None
    rest = rel[len(prefix) :]
    top = rest.split("/", 1)[0]
    return top if top in FRONTEND_FEATURES else None


def check_cross_feature_imports(
    files: list[Path],
    rel_fn: Callable[[Path], str],
    finding_cls: type,
) -> list:
    """Warn when a feature file imports another feature's internals."""
    findings = []
    for path in files:
        if path.suffix not in {".ts", ".tsx"} or _is_test(path):
            continue
        rel = rel_fn(path)
        src_feat = _feature_of(rel)
        if not src_feat:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in CROSS_FEATURE_RE.finditer(text):
            target = match.group(1)
            if target == src_feat:
                continue
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                finding_cls(
                    kind="cross_feature_import",
                    path=rel,
                    detail=f"{src_feat} imports internals of {target}",
                    line=line,
                    baseline=False,  # fingerprint baselines applied in run_checks
                )
            )
    return findings
