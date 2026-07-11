"""Obsidian recall guarantees: no stale paraphrase notes, no Whisper leakage."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from obsidian_store import DEFAULT_VAULT, _iter_note_files

TIMESTAMP_ROW = re.compile(r"^- \d{2}:\d{2}:\d{2} — ", re.MULTILINE)


@pytest.mark.skipif(not DEFAULT_VAULT.exists(), reason="no Obsidian vault on this machine")
def test_vault_contains_no_transcript_or_paraphrase_bodies() -> None:
    """Course text must live only in gitignored downloads/, never in the vault."""
    for path in DEFAULT_VAULT.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "minute-by-minute-paraphrase" not in text, f"{path} is a stale paraphrase note"
        assert not TIMESTAMP_ROW.search(text), (
            f"{path} contains timestamped transcript rows — paid course text must not be committed"
        )


@pytest.mark.skipif(not DEFAULT_VAULT.exists(), reason="no Obsidian vault on this machine")
def test_recall_index_excludes_whisper_and_scratch_files() -> None:
    """Only official-caption transcripts may join vault notes in keyword recall."""
    for path, rel, folder in _iter_note_files(DEFAULT_VAULT):
        if folder != "transcripts":
            continue
        head = path.read_text(encoding="utf-8")[:800]
        assert "source: warrior-trading-official-captions" in head, (
            f"{rel} joined recall without official-caption provenance"
        )
        assert "source: whisper-local-audio" not in head, f"{rel} is a Whisper file"
