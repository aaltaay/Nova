"""Shared helpers for Nova built-in security checks (ADR 004)."""
from __future__ import annotations

import re
from pathlib import Path

from tools.security_lib.redact import redact

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SOURCE = "nova-builtin"


def rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def location(path: str, line: int | None) -> str:
    if line:
        return f"{path}:{line}"
    return path


def line_of(text: str, match: re.Match[str]) -> int:
    return text.count("\n", 0, match.start()) + 1


__all__ = [
    "REPO_ROOT",
    "SOURCE",
    "line_of",
    "location",
    "read",
    "redact",
    "rel",
]
