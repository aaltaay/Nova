"""Obsidian vault helpers — keyword search over curated markdown notes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from constants import REPO_ROOT

DEFAULT_VAULT = REPO_ROOT / "knowledge" / "obsidian"

# Prefer decision notes over system docs when ranking.
FOLDER_WEIGHT = {
    "03-Nova-Decisions": 3.0,
    "02-Strategies": 2.5,
    "01-Courses": 1.5,
    "00-System": 0.5,
}


@dataclass
class NoteHit:
    path: str
    title: str
    score: float
    snippet: str
    folder: str


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in {"the", "and", "for", "with", "that", "this"}]


def search_obsidian(query: str, vault: Path | None = None, limit: int = 6) -> list[NoteHit]:
    vault = vault or DEFAULT_VAULT
    if not vault.exists():
        return []
    tokens = _tokenize(query)
    if not tokens:
        return []

    hits: list[NoteHit] = []
    for path in vault.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        lower = text.lower()
        raw = sum(lower.count(tok) for tok in tokens)
        if raw <= 0:
            continue
        rel = path.relative_to(vault)
        folder = rel.parts[0] if rel.parts else ""
        weight = FOLDER_WEIGHT.get(folder, 1.0)
        # Boost title / filename matches
        name_l = path.stem.lower().replace("-", " ")
        title_boost = 2.0 if any(tok in name_l for tok in tokens) else 1.0
        score = raw * weight * title_boost

        # Snippet around first token hit
        snippet = text.strip()
        for tok in tokens:
            idx = lower.find(tok)
            if idx >= 0:
                start = max(0, idx - 120)
                end = min(len(text), idx + 280)
                snippet = text[start:end].strip()
                break
        if len(snippet) > 500:
            snippet = snippet[:500] + "…"

        hits.append(
            NoteHit(
                path=str(rel).replace("\\", "/"),
                title=path.stem.replace("-", " "),
                score=score,
                snippet=snippet,
                folder=folder,
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]
