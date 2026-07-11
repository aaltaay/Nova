"""Split page text into overlapping chunks for embedding."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from constants import CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS, MIN_CHUNK_CHARS
from extract import PageDoc


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    course: str
    chapter: str
    filename: str
    layout: str
    page: int
    chunk_index: int
    rel_path: str
    source: str = "warrior-trading-slides"
    unit: str = ""
    timestamp_start: str = ""


def _chunk_id(rel_path: str, page: int, chunk_index: int, text: str) -> str:
    digest = hashlib.sha1(f"{rel_path}|{page}|{chunk_index}|{text[:80]}".encode()).hexdigest()[:16]
    safe = rel_path.replace("/", "_").replace(" ", "_")[:80]
    return f"{safe}_p{page}_c{chunk_index}_{digest}"


def chunk_page(page: PageDoc) -> list[Chunk]:
    text = page.text.strip()
    if len(text) < MIN_CHUNK_CHARS:
        return []

    if len(text) <= CHUNK_MAX_CHARS:
        return [
            Chunk(
                id=_chunk_id(page.rel_path, page.page, 0, text),
                text=text,
                course=page.course,
                chapter=page.chapter,
                filename=page.filename,
                layout=page.layout,
                page=page.page,
                chunk_index=0,
                rel_path=page.rel_path,
                source=page.source,
                unit=page.unit,
                timestamp_start=page.timestamp_start,
            )
        ]

    chunks: list[Chunk] = []
    start = 0
    index = 0
    while start < len(text):
        end = min(start + CHUNK_MAX_CHARS, len(text))
        # Prefer breaking on paragraph / sentence boundaries
        if end < len(text):
            window = text[start:end]
            break_at = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"))
            if break_at > CHUNK_MAX_CHARS // 3:
                end = start + break_at + 1
        piece = text[start:end].strip()
        if len(piece) >= MIN_CHUNK_CHARS:
            chunks.append(
                Chunk(
                    id=_chunk_id(page.rel_path, page.page, index, piece),
                    text=piece,
                    course=page.course,
                    chapter=page.chapter,
                    filename=page.filename,
                    layout=page.layout,
                    page=page.page,
                    chunk_index=index,
                    rel_path=page.rel_path,
                    source=page.source,
                    unit=page.unit,
                    timestamp_start=page.timestamp_start,
                )
            )
            index += 1
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP_CHARS, start + 1)
    return chunks


def chunk_pages(pages: list[PageDoc]) -> list[Chunk]:
    out: list[Chunk] = []
    for page in pages:
        out.extend(chunk_page(page))
    return out
