"""Deterministic documentation / canvas inventory for Docs.

Side-effect-free: classifies Cursor canvases and lists documentation roots.
Does not implement prose/style/link standards (those belong to markdownlint,
Vale, and Lychee).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Managed Cursor canvases directory (Windows default for this workspace).
DEFAULT_CANVASES_DIR = Path.home() / ".cursor" / "projects" / "c-Users-aalta-github-Nova" / "canvases"

PREFERRED_HOME = "nova-home.canvas.tsx"
AGENT_CANVAS_RE = re.compile(r"^agent-.+\.canvas\.tsx$")
SYSTEM_CANVAS_RE = re.compile(r"^context-usage-.+\.canvas\.tsx$")

DOC_ROOTS = (
    "docs",
    "knowledge/obsidian",
    ".cursor/agents",
    ".cursor/rules",
)

DOC_ROOT_FILES = (
    "AGENTS.md",
    "gemini.md",
    "README.md",
)


@dataclass
class CanvasEntry:
    name: str
    kind: str  # preferred_home | preferred_agent | system | unmanaged
    path: str


@dataclass
class InventoryReport:
    canvases_dir: str
    preferred: list[CanvasEntry]
    system: list[CanvasEntry]
    unmanaged: list[CanvasEntry]
    doc_roots_present: list[str]
    doc_root_files_present: list[str]


def classify_canvas_name(name: str) -> str:
    """Return preferred_home | preferred_agent | system | unmanaged."""
    if name == PREFERRED_HOME:
        return "preferred_home"
    if AGENT_CANVAS_RE.match(name):
        return "preferred_agent"
    if SYSTEM_CANVAS_RE.match(name):
        return "system"
    if name.endswith(".canvas.tsx"):
        return "unmanaged"
    return "unmanaged"


def resolve_canvases_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get("NOVA_CANVASES_DIR")
    if env:
        return Path(env)
    return DEFAULT_CANVASES_DIR


def list_canvas_files(canvases_dir: Path) -> list[Path]:
    if not canvases_dir.is_dir():
        return []
    return sorted(canvases_dir.glob("*.canvas.tsx"))


def inventory_canvases(canvases_dir: Path) -> tuple[list[CanvasEntry], list[CanvasEntry], list[CanvasEntry]]:
    preferred: list[CanvasEntry] = []
    system: list[CanvasEntry] = []
    unmanaged: list[CanvasEntry] = []
    for path in list_canvas_files(canvases_dir):
        kind = classify_canvas_name(path.name)
        entry = CanvasEntry(name=path.name, kind=kind, path=str(path))
        if kind in ("preferred_home", "preferred_agent"):
            preferred.append(entry)
        elif kind == "system":
            system.append(entry)
        else:
            unmanaged.append(entry)
    return preferred, system, unmanaged


def inventory_doc_roots(repo_root: Path = REPO_ROOT) -> tuple[list[str], list[str]]:
    roots = [r for r in DOC_ROOTS if (repo_root / r).exists()]
    files = [f for f in DOC_ROOT_FILES if (repo_root / f).is_file()]
    return roots, files


def build_report(canvases_dir: Path | None = None, repo_root: Path = REPO_ROOT) -> InventoryReport:
    cdir = resolve_canvases_dir(canvases_dir)
    preferred, system, unmanaged = inventory_canvases(cdir)
    roots, files = inventory_doc_roots(repo_root)
    return InventoryReport(
        canvases_dir=str(cdir),
        preferred=preferred,
        system=system,
        unmanaged=unmanaged,
        doc_roots_present=roots,
        doc_root_files_present=files,
    )


def format_human(report: InventoryReport) -> str:
    lines = [
        "Nova docs / canvas inventory",
        f"Canvases dir: {report.canvases_dir}",
        "",
        f"Preferred ({len(report.preferred)}):",
    ]
    for e in report.preferred:
        lines.append(f"  [{e.kind}] {e.name}")
    lines.append(f"System ({len(report.system)}):")
    for e in report.system:
        lines.append(f"  [{e.kind}] {e.name}")
    lines.append(f"Unmanaged ({len(report.unmanaged)}):")
    if not report.unmanaged:
        lines.append("  (none)")
    else:
        for e in report.unmanaged:
            lines.append(f"  [{e.kind}] {e.name}")
    lines.append("")
    lines.append("Doc roots present: " + (", ".join(report.doc_roots_present) or "(none)"))
    lines.append("Doc root files present: " + (", ".join(report.doc_root_files_present) or "(none)"))
    return "\n".join(lines) + "\n"


def to_jsonable(report: InventoryReport) -> dict:
    return {
        "canvases_dir": report.canvases_dir,
        "preferred": [asdict(e) for e in report.preferred],
        "system": [asdict(e) for e in report.system],
        "unmanaged": [asdict(e) for e in report.unmanaged],
        "doc_roots_present": report.doc_roots_present,
        "doc_root_files_present": report.doc_root_files_present,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova documentation / canvas inventory")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument(
        "--canvases-dir",
        type=Path,
        default=None,
        help="Override canvases directory (default: Cursor managed path or NOVA_CANVASES_DIR)",
    )
    parser.add_argument(
        "--fail-on-unmanaged",
        action="store_true",
        help="Exit 1 when unmanaged canvases exist",
    )
    args = parser.parse_args(argv)

    report = build_report(canvases_dir=args.canvases_dir)
    if args.json:
        print(json.dumps(to_jsonable(report), indent=2))
    else:
        print(format_human(report))

    if args.fail_on_unmanaged and report.unmanaged:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
