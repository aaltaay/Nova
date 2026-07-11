"""Extract text + metadata from course slide PDFs."""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from constants import DEFAULT_PDF_ROOT, PREFERRED_SLIDE_LAYOUT


@dataclass(frozen=True)
class PageDoc:
    course: str
    chapter: str
    filename: str
    layout: str  # 1pp | 2pp | other
    page: int
    text: str
    rel_path: str
    source: str = "warrior-trading-slides"
    unit: str = ""
    timestamp_start: str = ""


_LAYOUT_RE = re.compile(r"-(1pp|2pp)\.pdf$", re.IGNORECASE)


def _layout_of(path: Path) -> str:
    match = _LAYOUT_RE.search(path.name)
    return match.group(1).lower() if match else "other"


def _course_chapter(path: Path, root: Path) -> tuple[str, str]:
    rel = path.relative_to(root)
    parts = rel.parts
    course = parts[0] if parts else "unknown"
    chapter = parts[1] if len(parts) > 2 else (parts[1] if len(parts) > 1 else "root")
    # File directly under course (no chapter folder)
    if len(parts) == 2:
        chapter = "root"
    return course, chapter


def iter_pdfs(root: Path | None = None, layout: str = PREFERRED_SLIDE_LAYOUT) -> list[Path]:
    root = root or DEFAULT_PDF_ROOT
    if not root.exists():
        raise FileNotFoundError(f"PDF root not found: {root}")
    pdfs = sorted(root.rglob("*.pdf"))
    if layout and layout != "all":
        pdfs = [p for p in pdfs if _layout_of(p) == layout]
    return pdfs


def extract_pages(pdf_path: Path, root: Path | None = None) -> list[PageDoc]:
    root = root or DEFAULT_PDF_ROOT
    course, chapter = _course_chapter(pdf_path, root)
    layout = _layout_of(pdf_path)
    pages: list[PageDoc] = []
    # Some Warrior PDFs have malformed numeric objects; pypdf still extracts text.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        reader = PdfReader(str(pdf_path), strict=False)
        for i, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""
            text = re.sub(r"[ \t]+", " ", raw)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if not text:
                continue
            pages.append(
                PageDoc(
                    course=course,
                    chapter=chapter,
                    filename=pdf_path.name,
                    layout=layout,
                    page=i,
                    text=text,
                    rel_path=str(pdf_path.relative_to(root)).replace("\\", "/"),
                )
            )
    return pages
