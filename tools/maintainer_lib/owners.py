"""Who owns what: every backend package and every frontend folder says so.

AGENTS.md §2.1 / §2.2. A hand-kept file tree in the constitution went stale
(11 of its 24 files were gone by 2026-09-20), so the statement lives next to
the code instead and this check keeps it complete:

* a backend package's ``__init__.py`` opens with a docstring naming what it owns;
* every top-level ``frontend/src/`` folder has a row in ``frontend/src/FOLDERS.md``
  and every row names a folder that exists.

The FOLDERS.md kinds also define which folders are features for the
cross-feature import check (ADR 005), so the list is used, not decorative.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

FOLDERS_MANIFEST = "frontend/src/FOLDERS.md"
FOLDER_KINDS = frozenset({"feature", "shared", "app"})
_ROW_RE = re.compile(r"^\|\s*`(?P<folder>[\w.-]+)/`\s*\|\s*(?P<kind>\w+)\s*\|\s*(?P<owns>.+?)\s*\|\s*$")
_SKIP_DIRS = frozenset({"__pycache__", "node_modules", "tests", "dist", "coverage"})


def parse_manifest(text: str) -> dict[str, tuple[str, str]]:
    """``{folder: (kind, owns)}`` from the FOLDERS.md table."""
    rows: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        match = _ROW_RE.match(line.strip())
        if match:
            rows[match.group("folder")] = (match.group("kind"), match.group("owns"))
    return rows


def load_manifest(repo_root: Path) -> dict[str, tuple[str, str]] | None:
    path = repo_root / FOLDERS_MANIFEST
    if not path.is_file():
        return None
    return parse_manifest(path.read_text(encoding="utf-8"))


def feature_folders(repo_root: Path) -> tuple[str, ...]:
    rows = load_manifest(repo_root) or {}
    return tuple(sorted(name for name, (kind, _owns) in rows.items() if kind == "feature"))


def package_docstring(init_path: Path) -> str | None:
    """First line of the package docstring, None when there is none."""
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return None
    doc = ast.get_docstring(tree)
    if not doc or not doc.strip():
        return None
    return doc.strip().splitlines()[0].strip()


def backend_packages(repo_root: Path) -> list[Path]:
    backend = repo_root / "backend"
    if not backend.is_dir():
        return []
    return sorted(
        init.parent for init in backend.rglob("__init__.py")
        if not (set(init.relative_to(backend).parts[:-1]) & _SKIP_DIRS)
    )


def frontend_folders(repo_root: Path) -> list[str]:
    src = repo_root / "frontend" / "src"
    if not src.is_dir():
        return []
    return sorted(
        child.name for child in src.iterdir()
        if child.is_dir() and child.name not in _SKIP_DIRS
        and any(p.is_file() for p in child.rglob("*"))
    )


def check_owners(repo_root: Path, finding_cls: type) -> list:
    findings = []
    for package in backend_packages(repo_root):
        rel = package.relative_to(repo_root).as_posix()
        if package_docstring(package / "__init__.py") is None:
            findings.append(finding_cls(
                kind="package_owner_missing", path=f"{rel}/__init__.py",
                detail="package has no docstring saying what it owns (AGENTS.md §2.1)",
            ))
    rows = load_manifest(repo_root)
    if rows is None:
        findings.append(finding_cls(
            kind="folder_owner_missing", path=FOLDERS_MANIFEST,
            detail="the frontend folder list is missing (AGENTS.md §2.2)",
        ))
        return findings
    present = set(frontend_folders(repo_root))
    for folder in sorted(present - set(rows)):
        findings.append(finding_cls(
            kind="folder_owner_missing", path=f"frontend/src/{folder}/",
            detail=f"no row in {FOLDERS_MANIFEST} saying what this folder owns",
        ))
    for folder in sorted(set(rows) - present):
        findings.append(finding_cls(
            kind="folder_owner_stale", path=FOLDERS_MANIFEST,
            detail=f"row for `{folder}/`, which no longer exists -- remove it",
        ))
    for folder, (kind, _owns) in sorted(rows.items()):
        if kind not in FOLDER_KINDS:
            findings.append(finding_cls(
                kind="folder_owner_stale", path=FOLDERS_MANIFEST,
                detail=f"`{folder}/` has kind `{kind}`; use one of {sorted(FOLDER_KINDS)}",
            ))
    return findings


def module_map(repo_root: Path) -> dict[str, list[dict[str, str]]]:
    """Backend packages and frontend folders with what each owns."""
    backend = []
    for package in backend_packages(repo_root):
        backend.append({
            "path": package.relative_to(repo_root).as_posix() + "/",
            "owns": package_docstring(package / "__init__.py") or "(no docstring)",
        })
    frontend = [
        {"path": f"frontend/src/{folder}/", "kind": kind, "owns": owns}
        for folder, (kind, owns) in sorted((load_manifest(repo_root) or {}).items())
    ]
    return {"backend": backend, "frontend": frontend}
