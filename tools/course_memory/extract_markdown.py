"""Extract section text and provenance from curated course Markdown."""

from __future__ import annotations

import re
from pathlib import Path

from constants import DEFAULT_MARKDOWN_ROOT
from extract import PageDoc

_FRONTMATTER_BOUNDARY = "---"
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_TIMESTAMP_RE = re.compile(r"\b(?:\d{1,2}:)?\d{2}:\d{2}\b")


def iter_markdown(root: Path | None = None) -> list[Path]:
    root = root or DEFAULT_MARKDOWN_ROOT
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*.md")
        if path.name.upper() != "COURSE_INVENTORY.MD"
        and not path.name.startswith("_")
    )


def frontmatter_source(path: Path) -> str:
    """Return the frontmatter ``source`` field, or empty string."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    meta, _ = _frontmatter(text)
    return meta.get("source", "")


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith(f"{_FRONTMATTER_BOUNDARY}\n"):
        return {}, text
    closing = text.find(f"\n{_FRONTMATTER_BOUNDARY}\n", len(_FRONTMATTER_BOUNDARY) + 1)
    if closing < 0:
        return {}, text

    values: dict[str, str] = {}
    for line in text[len(_FRONTMATTER_BOUNDARY) + 1 : closing].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip().lower()] = value.strip().strip("\"'")
    return values, text[closing + len(_FRONTMATTER_BOUNDARY) + 2 :].lstrip()


def _sections(text: str) -> list[tuple[str, str]]:
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        title_match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
        title = title_match.group(1) if title_match else "Overview"
        return [(title, text.strip())]

    sections: list[tuple[str, str]] = []
    preface = text[: matches[0].start()].strip()
    if preface:
        title_match = re.search(r"^#\s+(.+?)\s*$", preface, re.MULTILINE)
        sections.append((title_match.group(1) if title_match else "Overview", preface))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        sections.append((match.group(1).strip(), f"## {match.group(1).strip()}\n\n{body}".strip()))
    return sections


def extract_markdown_sections(markdown_path: Path, root: Path | None = None) -> list[PageDoc]:
    root = root or DEFAULT_MARKDOWN_ROOT
    metadata, content = _frontmatter(markdown_path.read_text(encoding="utf-8"))
    course = metadata.get("course", markdown_path.stem)
    source = metadata.get("source", "warrior-trading-official-captions")
    unit_meta = metadata.get("unit", "")
    rel_path = str(markdown_path.relative_to(root)).replace("\\", "/")

    docs: list[PageDoc] = []
    for section_number, (heading, text) in enumerate(_sections(content), start=1):
        timestamp = _TIMESTAMP_RE.search(text)
        unit = unit_meta or heading
        docs.append(
            PageDoc(
                course=course,
                chapter=heading,
                filename=markdown_path.name,
                layout="markdown",
                page=section_number,
                text=text,
                rel_path=rel_path,
                source=source,
                unit=unit,
                timestamp_start=timestamp.group(0) if timestamp else "",
            )
        )
    return docs
