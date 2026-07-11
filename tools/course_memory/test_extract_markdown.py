"""Tests for timestamped course Markdown extraction."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chunk import chunk_pages
from export_unit_notes import export_unit_notes
from extract_markdown import extract_markdown_sections, iter_markdown
from pinecone_store import chunk_to_record
from recall import format_pinecone_match


def test_extracts_frontmatter_sections_and_timestamp(tmp_path: Path) -> None:
    note = tmp_path / "course.md"
    note.write_text(
        """---
course: Day Trading - The Basics
source: warrior-trading-caption-notes
---
# Notes

## Chapter 1

- 00:04:28 — Career roadmap
- Practice in simulation before scaling position size.

## Chapter 2

No timestamp in this section, but enough text to become a searchable document.
""",
        encoding="utf-8",
    )

    docs = extract_markdown_sections(note, tmp_path)

    assert [doc.chapter for doc in docs] == ["Notes", "Chapter 1", "Chapter 2"]
    assert docs[1].course == "Day Trading - The Basics"
    assert docs[1].source == "warrior-trading-caption-notes"
    assert docs[1].timestamp_start == "00:04:28"
    assert docs[2].timestamp_start == ""


def test_iter_markdown_returns_nested_files(tmp_path: Path) -> None:
    nested = tmp_path / "course"
    nested.mkdir()
    (nested / "notes.md").write_text("# Notes", encoding="utf-8")
    (nested / "ignore.txt").write_text("not markdown", encoding="utf-8")

    assert iter_markdown(tmp_path) == [nested / "notes.md"]


def test_chunk_record_preserves_markdown_provenance(tmp_path: Path) -> None:
    note = tmp_path / "course.md"
    note.write_text(
        """---
course: Scanning 101
source: warrior-trading-caption-notes
---
## Scanner workflow

00:01:48 — Confirm that price movement supports the news catalyst before considering a setup.
""",
        encoding="utf-8",
    )
    chunks = chunk_pages(extract_markdown_sections(note, tmp_path))

    assert len(chunks) == 1
    record = chunk_to_record(chunks[0], [0.0, 0.1])
    assert record["metadata"]["source"] == "warrior-trading-caption-notes"
    assert record["metadata"]["unit"] == "Scanner workflow"
    assert record["metadata"]["timestamp_start"] == "00:01:48"


def test_chunk_ids_are_stable_for_same_markdown(tmp_path: Path) -> None:
    note = tmp_path / "course.md"
    note.write_text(
        "## Setup\n\n00:00:10 — Stable content for repeatable chunk identifiers across repeated extraction runs.",
        encoding="utf-8",
    )

    first = chunk_pages(extract_markdown_sections(note, tmp_path))
    second = chunk_pages(extract_markdown_sections(note, tmp_path))

    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]


def test_exports_one_file_per_captioned_unit(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    output_root = tmp_path / "output"
    source_root.mkdir()
    (source_root / "SS101-Timestamped-Notes.md").write_text(
        """---
course: 2. Day Trading - Strategies & Scaling
source: warrior-trading-caption-notes
---
# SS101 Timestamped Notes

## Risk Management

- 00:02:17 — Risk categories

## Caption gaps

No captions elsewhere.
""",
        encoding="utf-8",
    )

    written = export_unit_notes(source_root, output_root)

    assert len(written) == 1
    exported = written[0].read_text(encoding="utf-8")
    assert written[0].name == "risk-management.md"
    assert "unit: Risk Management" in exported
    assert "# Risk Management" in exported


def test_formats_slide_and_caption_note_citations() -> None:
    slide = format_pinecone_match(
        {
            "score": 0.5,
            "course": "Course",
            "chapter": "Chapter 1",
            "page": 12,
            "text": "Slide text",
            "source": "warrior-trading-slides",
            "rel_path": "slides.pdf",
        },
        1,
    )
    note = format_pinecone_match(
        {
            "score": 0.6,
            "course": "Course",
            "chapter": "Risk",
            "timestamp_start": "00:02:17",
            "text": "Caption-derived note",
            "source": "warrior-trading-caption-notes",
            "rel_path": "risk.md",
        },
        2,
    )

    assert "Chapter 1 p12" in slide
    assert "warrior-trading-slides | slides.pdf" in slide
    assert "Risk @ 00:02:17" in note
    assert "warrior-trading-caption-notes | risk.md" in note
