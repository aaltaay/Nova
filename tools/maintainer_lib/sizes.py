"""Line counting for the size checks.

Entry points (`backend/main.py`, `frontend/src/App.tsx`) are measured in
*logical* lines -- imports, comments and blank lines are not counted -- because
the rule exists to keep wiring-only files wiring-only, not to cap how many
providers an app may import. Raw counting made `App.tsx` a breach at 152 lines
of which 30 were imports and 14 were comments (#393), while leaving no alarm
for 50 lines of real logic. Everything else still counts raw lines.

`frontend/src/index.css` keeps a raw limit: it is an import manifest, where the
raw line is the thing being limited.
"""
from __future__ import annotations

from pathlib import Path

# Entry points measured in logical lines.
LOGICAL_LIMIT_FILES = ("backend/main.py", "frontend/src/App.tsx")

_PY_IMPORT_PREFIXES = ("import ", "from ")
_TS_IMPORT_PREFIXES = ("import ", "export * from", "export { ", "export type ")


def _read(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()
    except OSError:
        return []


def count_logical_lines(path: Path) -> int:
    """Non-blank, non-import, non-comment lines.

    Deliberately a lexical approximation, not a parse: it must agree with what
    a reader counts by eye, and it must never crash the checker on a file that
    does not compile.
    """
    suffix = path.suffix.lower()
    python = suffix == ".py"
    prefixes = _PY_IMPORT_PREFIXES if python else _TS_IMPORT_PREFIXES
    total = 0
    in_block = False
    for raw in _read(path):
        line = raw.strip()
        if in_block:
            # A block comment/docstring terminator can be followed by code.
            end = '"""' if python else "*/"
            if end in line:
                in_block = False
                line = line.split(end, 1)[1].strip()
                if not line:
                    continue
            else:
                continue
        if not line:
            continue
        if python and (line.startswith('"""') or line.startswith("'''")):
            quote = line[:3]
            if len(line) < 6 or not line.endswith(quote):
                in_block = True
            continue
        if not python and line.startswith("/*"):
            if "*/" not in line:
                in_block = True
            continue
        if line.startswith("#" if python else "//") or line.startswith("*"):
            continue
        if line.startswith(prefixes) or line.startswith("} from "):
            continue
        # A multi-line import's continuation lines are not logic either.
        if not python and (line in ("} from", "}") or line.endswith("';") and "from '" in line):
            continue
        total += 1
    return total
