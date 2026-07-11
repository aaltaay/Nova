"""Ingest Warrior Trading PDFs and curated Markdown into Pinecone memory."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running as `py ingest.py` from this directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

from chunk import chunk_pages
from constants import (
    DEFAULT_CAPTION_EXPORT_ROOT,
    DEFAULT_MARKDOWN_ROOT,
    DEFAULT_NAMESPACE,
    DEFAULT_PDF_ROOT,
    OFFICIAL_TRANSCRIPT_SOURCES,
    PREFERRED_SLIDE_LAYOUT,
    REPO_ROOT,
    STALE_CAPTION_SOURCES,
    env,
)
from embed import embed_texts
from extract import extract_pages, iter_pdfs
from extract_markdown import extract_markdown_sections, frontmatter_source, iter_markdown
from pinecone_store import delete_by_source, ensure_index, get_pinecone, upsert_chunks


def _load_env() -> None:
    load_dotenv(REPO_ROOT / ".env")


def _filter_markdown(
    paths: list[Path],
    allowed_sources: set[str] | None,
) -> list[Path]:
    if not allowed_sources:
        return paths
    kept: list[Path] = []
    for path in paths:
        source = frontmatter_source(path)
        if source in allowed_sources:
            kept.append(path)
    return kept


def ingest(
    pdf_root: Path,
    layout: str,
    limit: int | None,
    dry_run: bool,
    *,
    markdown_root: Path = DEFAULT_MARKDOWN_ROOT,
    content: str = "pdf",
    markdown_sources: set[str] | None = None,
    purge_sources: list[str] | None = None,
) -> None:
    _load_env()
    all_chunks = []
    if content in {"pdf", "all"}:
        pdfs = iter_pdfs(pdf_root, layout=layout)
        if limit:
            pdfs = pdfs[:limit]
        print(f"PDF root: {pdf_root}")
        print(f"Layout filter: {layout}")
        print(f"PDFs to process: {len(pdfs)}")
        for i, pdf in enumerate(pdfs, start=1):
            pages = extract_pages(pdf, pdf_root)
            chunks = chunk_pages(pages)
            print(
                f"[PDF {i}/{len(pdfs)}] {pdf.relative_to(pdf_root)} "
                f"-> {len(pages)} pages, {len(chunks)} chunks"
            )
            all_chunks.extend(chunks)

    if content in {"markdown", "all"}:
        markdown_files = iter_markdown(markdown_root)
        markdown_files = _filter_markdown(markdown_files, markdown_sources)
        if limit:
            markdown_files = markdown_files[:limit]
        print(f"Markdown root: {markdown_root}")
        if markdown_sources:
            print(f"Markdown source filter: {sorted(markdown_sources)}")
        print(f"Markdown files to process: {len(markdown_files)}")
        for i, markdown_file in enumerate(markdown_files, start=1):
            sections = extract_markdown_sections(markdown_file, markdown_root)
            chunks = chunk_pages(sections)
            print(
                f"[Markdown {i}/{len(markdown_files)}] {markdown_file.relative_to(markdown_root)} "
                f"-> {len(sections)} sections, {len(chunks)} chunks "
                f"(source={sections[0].source if sections else '?'})"
            )
            all_chunks.extend(chunks)

    print(f"Total chunks: {len(all_chunks)}")
    if dry_run:
        courses = sorted({c.course for c in all_chunks})
        sources = sorted({c.source for c in all_chunks})
        print("Courses:", ", ".join(courses))
        print("Sources:", ", ".join(sources))
        print("Dry run — no embeddings / upsert.")
        return

    if not env("PINECONE_API_KEY") or not env("OPENAI_API_KEY"):
        raise SystemExit(
            "Missing keys. Set PINECONE_API_KEY and OPENAI_API_KEY in the repo .env, then re-run."
        )

    pc = get_pinecone()
    index_name = ensure_index(pc)
    namespace = env("PINECONE_NAMESPACE", DEFAULT_NAMESPACE) or DEFAULT_NAMESPACE
    print(f"Pinecone index: {index_name}")
    print(f"Namespace: {namespace}")

    if purge_sources:
        print(f"Purging stale sources: {purge_sources}")
        delete_by_source(purge_sources, namespace=namespace)

    if not all_chunks:
        print("Nothing to upsert.")
        return

    texts = [c.text for c in all_chunks]
    t0 = time.time()
    vectors = embed_texts(texts)
    print(f"Embedded {len(vectors)} chunks in {time.time() - t0:.1f}s")

    t1 = time.time()
    upserted = upsert_chunks(all_chunks, vectors)
    print(f"Upserted {upserted} vectors in {time.time() - t1:.1f}s")
    print("Done. Query with: py recall.py --source pinecone \"your question\"")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest course PDFs and curated Markdown into Pinecone"
    )
    parser.add_argument("--content", choices=["pdf", "markdown", "all"], default="pdf")
    parser.add_argument("--pdf-root", type=Path, default=DEFAULT_PDF_ROOT)
    parser.add_argument("--markdown-root", type=Path, default=DEFAULT_MARKDOWN_ROOT)
    parser.add_argument(
        "--layout",
        default=PREFERRED_SLIDE_LAYOUT,
        help="1pp (default), 2pp, or all",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Process only first N files per source"
    )
    parser.add_argument("--dry-run", action="store_true", help="Extract/chunk only, no upsert")
    parser.add_argument(
        "--official-transcripts",
        action="store_true",
        help=(
            "Ingest only official LMS caption transcripts from "
            "downloads/warrior-trading-caption-notes, and purge stale caption-note vectors first."
        ),
    )
    parser.add_argument(
        "--include-whisper",
        action="store_true",
        help="With --official-transcripts, also index whisper-local-audio files (not 100%% accurate).",
    )
    parser.add_argument(
        "--purge-stale-captions",
        action="store_true",
        help="Delete old inaccurate caption-note vectors even if not upserting.",
    )
    args = parser.parse_args()

    markdown_root = args.markdown_root
    markdown_sources: set[str] | None = None
    purge_sources: list[str] | None = None
    content = args.content

    if args.official_transcripts:
        content = "markdown"
        markdown_root = DEFAULT_CAPTION_EXPORT_ROOT
        markdown_sources = set(OFFICIAL_TRANSCRIPT_SOURCES)
        if args.include_whisper:
            markdown_sources.add("whisper-local-audio")
        purge_sources = list(STALE_CAPTION_SOURCES)
    elif args.purge_stale_captions:
        purge_sources = list(STALE_CAPTION_SOURCES)

    ingest(
        args.pdf_root,
        args.layout,
        args.limit,
        args.dry_run,
        markdown_root=markdown_root,
        content=content,
        markdown_sources=markdown_sources,
        purge_sources=None if args.dry_run else purge_sources,
    )


if __name__ == "__main__":
    main()
