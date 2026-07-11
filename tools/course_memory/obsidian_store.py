"""Obsidian vault helpers — keyword search over curated markdown notes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from constants import DEFAULT_CAPTION_EXPORT_ROOT, REPO_ROOT

DEFAULT_VAULT = REPO_ROOT / "knowledge" / "obsidian"

# Prefer decision notes over system docs when ranking.
FOLDER_WEIGHT = {
    "03-Nova-Decisions": 3.0,
    "02-Strategies": 2.5,
    "01-Courses": 1.5,
    "00-System": 0.5,
    # Local official transcripts (gitignored downloads/) — high weight for course facts.
    "transcripts": 2.0,
}


@dataclass
class NoteHit:
    path: str
    title: str
    score: float
    snippet: str
    folder: str


def _tokenize(text: str) -> list[str]:
    return [
        t
        for t in re.findall(r"[a-z0-9]{3,}", text.lower())
        if t not in {"the", "and", "for", "with", "that", "this"}
    ]


def _iter_note_files(vault: Path) -> list[tuple[Path, str, str]]:
    """Return (path, display_rel, folder_key) for vault notes + official transcripts."""
    files: list[tuple[Path, str, str]] = []
    for path in vault.rglob("*.md"):
        rel = path.relative_to(vault)
        folder = rel.parts[0] if rel.parts else ""
        files.append((path, str(rel).replace("\\", "/"), folder))

    # Official LMS caption transcripts live under downloads/ (gitignored).
    transcript_root = DEFAULT_CAPTION_EXPORT_ROOT
    if transcript_root.exists():
        for path in transcript_root.rglob("*.md"):
            if path.name.upper() == "COURSE_INVENTORY.MD" or path.name.startswith("_"):
                continue
            try:
                text_head = path.read_text(encoding="utf-8")[:800]
            except OSError:
                continue
            if "source: warrior-trading-official-captions" not in text_head:
                continue
            rel = f"transcripts/{path.relative_to(transcript_root).as_posix()}"
            files.append((path, rel, "transcripts"))
    return files


def search_obsidian(query: str, vault: Path | None = None, limit: int = 6) -> list[NoteHit]:
    vault = vault or DEFAULT_VAULT
    if not vault.exists():
        return []
    tokens = _tokenize(query)
    if not tokens:
        return []

    hits: list[NoteHit] = []
    for path, display_rel, folder in _iter_note_files(vault):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        lower = text.lower()
        raw = sum(lower.count(tok) for tok in tokens)
        if raw <= 0:
            continue
        weight = FOLDER_WEIGHT.get(folder, 1.0)
        name_l = path.stem.lower().replace("-", " ")
        title_boost = 2.0 if any(tok in name_l for tok in tokens) else 1.0
        score = raw * weight * title_boost

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
                path=display_rel,
                title=path.stem.replace("-", " "),
                score=score,
                snippet=snippet,
                folder=folder,
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]
