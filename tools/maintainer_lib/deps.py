"""Architecture dependency checks (warning-first for legacy trees)."""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import Callable

FindingFactory = Callable[..., object]

IMPORT_MAIN_RE = re.compile(
    r"^[ \t]*(?:import\s+main(?:\s+as\s+\w+)?|from\s+main\s+import\s+.+)\s*(?:#.*)?$",
    re.MULTILINE,
)

# Feature slices under frontend/src (ADR 005) come from frontend/src/FOLDERS.md
# (kind `feature`), so a new slice is covered the moment it is listed. The
# hand-kept tuple this replaced named 9 slices, two of which no longer existed.
_REPO_ROOT = Path(__file__).resolve().parents[2]


# Any module specifier: `from '...'`, `import '...'`, `import('...')`.
_IMPORT_SPEC_RE = re.compile(r"""(?:\bfrom|\bimport)\s*\(?\s*['"]([^'"\n]+)['"]""")
_SRC = "frontend/src"


def deep_import_target(rel: str, spec: str, features: tuple[str, ...]) -> str | None:
    """The feature whose internals ``spec`` (imported from ``rel``) reaches.

    The path is resolved, so `../chart/x` from a nested folder that has its own
    `chart/` sibling is not mistaken for the chart slice. Importing a slice's
    barrel (`../chart`, `@/chart`) is its public API and returns None.
    """
    if spec.startswith("@/"):
        resolved = f"{_SRC}/{spec[2:]}"
    elif spec.startswith("../"):
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec))
    else:
        return None
    if not resolved.startswith(_SRC + "/"):
        return None
    parts = resolved[len(_SRC) + 1:].split("/")
    if len(parts) < 2 or parts[0] not in features or parts[1] in {"", "index"}:
        return None
    return parts[0]


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
                    baseline=False,  # count baselines applied in run_checks
                )
            )
    return findings


def _feature_of(rel: str, features: tuple[str, ...]) -> str | None:
    prefix = "frontend/src/"
    if not rel.startswith(prefix):
        return None
    rest = rel[len(prefix) :]
    top = rest.split("/", 1)[0]
    return top if top in features else None


def check_cross_feature_imports(
    files: list[Path],
    rel_fn: Callable[[Path], str],
    finding_cls: type,
    features: tuple[str, ...] | None = None,
) -> list:
    """Flag a feature file that imports another feature's internals."""
    if features is None:
        from maintainer_lib.owners import feature_folders

        features = feature_folders(_REPO_ROOT)
    if not features:
        return []
    findings = []
    for path in files:
        if path.suffix not in {".ts", ".tsx"} or _is_test(path):
            continue
        rel = rel_fn(path)
        src_feat = _feature_of(rel, features)
        if not src_feat:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _IMPORT_SPEC_RE.finditer(text):
            target = deep_import_target(rel, match.group(1), features)
            if target is None or target == src_feat:
                continue
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                finding_cls(
                    kind="cross_feature_import",
                    path=rel,
                    detail=f"{src_feat} imports internals of {target}",
                    line=line,
                    baseline=False,  # count baselines applied in run_checks
                )
            )
    return findings
