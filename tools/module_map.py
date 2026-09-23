"""Where does this code go? Print what every backend package and frontend folder owns.

AGENTS.md §2.1 / §2.2. Read-only. The statements come from the code itself --
each backend package's ``__init__.py`` docstring and the rows of
``frontend/src/FOLDERS.md`` -- and ``tools/maintainer_checks.py`` fails CI when
one is missing, so this map cannot drift from the tree the way the old
hand-kept file trees did.

    py -3 tools/module_map.py            # markdown tables
    py -3 tools/module_map.py --json
    py -3 tools/module_map.py catalyst   # only rows mentioning a word
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_DIR = str(REPO_ROOT / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

from maintainer_lib.owners import module_map  # noqa: E402


def _matches(row: dict[str, str], word: str) -> bool:
    return not word or word.lower() in " ".join(row.values()).lower()


def render(mapping: dict[str, list[dict[str, str]]], word: str = "") -> str:
    lines = ["## Backend packages (`backend/`)", "", "| Package | Owns |", "|---|---|"]
    lines += [f"| `{r['path']}` | {r['owns']} |" for r in mapping["backend"] if _matches(r, word)]
    lines += ["", "Top-level `backend/*.py` modules are not packages; new code goes in a package.", ""]
    lines += ["## Frontend folders (`frontend/src/FOLDERS.md`)", "", "| Folder | Kind | Owns |", "|---|---|---|"]
    lines += [
        f"| `{r['path']}` | {r['kind']} | {r['owns']} |"
        for r in mapping["frontend"] if _matches(r, word)
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("word", nargs="?", default="", help="only rows mentioning this word")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        # Docstrings carry em dashes; a Windows pipe defaults to a legacy code page.
        sys.stdout.reconfigure(encoding="utf-8")
    mapping = module_map(REPO_ROOT)
    if args.json:
        filtered = {k: [r for r in rows if _matches(r, args.word)] for k, rows in mapping.items()}
        json.dump(filtered, sys.stdout, indent=2)
        print()
    else:
        print(render(mapping, args.word))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
