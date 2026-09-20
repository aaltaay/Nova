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


def _opens_block(line: str, python: bool) -> str | None:
    """The delimiter that closes a block comment / docstring this line opens."""
    if python:
        for quote in ('"""', "'''"):
            if line.startswith(quote):
                # A one-line docstring opens and closes on the same line.
                return None if len(line) >= 6 and line.endswith(quote) else quote
        return None
    if line.startswith("/*"):
        return None if "*/" in line else "*/"
    return None


def _import_continues(line: str, python: bool) -> bool:
    """True when an import statement is left open at the end of this line.

    A multiline named import is still an import on every one of its lines.
    Counting the identifiers between its braces as logic meant an ordinary
    provider-import expansion could trip the blocking entry-point gate without
    adding a line of wiring.
    """
    if python:
        return line.count("(") > line.count(")")
    return "from " not in line and not line.rstrip().endswith(";")


def _import_ends(line: str, python: bool) -> bool:
    if python:
        return ")" in line
    return "from " in line or line.rstrip().endswith(";")


def count_logical_lines(path: Path) -> int:
    """Non-blank, non-import, non-comment lines.

    Deliberately a lexical approximation, not a parse: it must agree with what
    a reader counts by eye, and it must never crash the checker on a file that
    does not compile.
    """
    python = path.suffix.lower() == ".py"
    prefixes = _PY_IMPORT_PREFIXES if python else _TS_IMPORT_PREFIXES
    total = 0
    closer: str | None = None
    in_import = False
    for raw in _read(path):
        line = raw.strip()
        if closer is not None:
            # Match the delimiter that was actually opened -- searching for
            # `"""` after a `'''` docstring swallowed the rest of the file.
            if closer not in line:
                continue
            line = line.split(closer, 1)[1].strip()
            closer = None
            if not line:
                continue
        if in_import:
            in_import = not _import_ends(line, python)
            continue
        if not line:
            continue
        opened = _opens_block(line, python)
        if opened is not None:
            closer = opened
            continue
        if line.startswith(('"""', "'''") if python else ("/*",)):
            continue  # Self-closing docstring or block comment.
        if line.startswith("#" if python else "//") or line.startswith("*"):
            continue
        if line.startswith(prefixes):
            in_import = _import_continues(line, python)
            continue
        total += 1
    return total
