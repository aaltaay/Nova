"""Static guard: Advise must never import IBKR or the order SSOT."""
from __future__ import annotations

from pathlib import Path

_FORBIDDEN = (
    "import ibkr",
    "from ibkr",
    "execution.service",
    "place_order",
    "cancel_order",
)


def advise_source_paths() -> list[Path]:
    root = Path(__file__).resolve().parent
    return [path for path in root.rglob("*.py") if path.name != "safety.py"]


def forbidden_hits() -> list[str]:
    hits: list[str] = []
    for path in advise_source_paths():
        text = path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN:
            if needle in text:
                hits.append(f"{path.name}:{needle}")
    return hits
