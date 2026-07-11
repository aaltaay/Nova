"""Export curated course-note sections as one local Markdown file per unit."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from constants import DEFAULT_CAPTION_EXPORT_ROOT, DEFAULT_MARKDOWN_ROOT
from extract_markdown import extract_markdown_sections, iter_markdown

_SKIPPED_HEADINGS = {"Caption gaps", "Units without caption tracks"}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:100] or "unit"


def _is_unit_heading(heading: str) -> bool:
    normalized = heading.lower()
    is_index_heading = "timestamped" in normalized and "notes" in normalized
    return heading not in _SKIPPED_HEADINGS and not is_index_heading


def export_unit_notes(
    markdown_root: Path = DEFAULT_MARKDOWN_ROOT,
    output_root: Path = DEFAULT_CAPTION_EXPORT_ROOT,
) -> list[Path]:
    written: list[Path] = []
    for source_path in iter_markdown(markdown_root):
        course_code = source_path.stem.split("-", 1)[0]
        for doc in extract_markdown_sections(source_path, markdown_root):
            if not _is_unit_heading(doc.chapter):
                continue
            destination = output_root / course_code / f"{_slug(doc.chapter)}.md"
            destination.parent.mkdir(parents=True, exist_ok=True)
            body = doc.text
            if body.startswith("## "):
                body = f"# {body[3:]}"
            destination.write_text(
                "\n".join(
                    [
                        "---",
                        f"course: {doc.course}",
                        f"course_code: {course_code}",
                        f"source: {doc.source}",
                        f"unit: {doc.chapter}",
                        "---",
                        body,
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            written.append(destination)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Export one timestamped Markdown file per captioned unit")
    parser.add_argument("--markdown-root", type=Path, default=DEFAULT_MARKDOWN_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_CAPTION_EXPORT_ROOT)
    args = parser.parse_args()

    written = export_unit_notes(args.markdown_root, args.output_root)
    print(f"Exported {len(written)} unit notes to {args.output_root}")
    for path in written:
        print(path.relative_to(args.output_root))


if __name__ == "__main__":
    main()
