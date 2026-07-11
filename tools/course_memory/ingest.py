"""Ingest Warrior Trading slide PDFs into Pinecone long-term memory."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Allow running as `py ingest.py` from this directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

from chunk import chunk_pages
from constants import DEFAULT_NAMESPACE, DEFAULT_PDF_ROOT, PREFERRED_SLIDE_LAYOUT, REPO_ROOT, env
from embed import embed_texts
from extract import extract_pages, iter_pdfs
from pinecone_store import ensure_index, get_pinecone, upsert_chunks


def _load_env() -> None:
    load_dotenv(REPO_ROOT / ".env")


def ingest(pdf_root: Path, layout: str, limit: int | None, dry_run: bool) -> None:
    _load_env()
    pdfs = iter_pdfs(pdf_root, layout=layout)
    if limit:
        pdfs = pdfs[:limit]
    print(f"PDF root: {pdf_root}")
    print(f"Layout filter: {layout}")
    print(f"PDFs to process: {len(pdfs)}")

    all_chunks = []
    for i, pdf in enumerate(pdfs, start=1):
        pages = extract_pages(pdf, pdf_root)
        chunks = chunk_pages(pages)
        print(f"[{i}/{len(pdfs)}] {pdf.relative_to(pdf_root)} -> {len(pages)} pages, {len(chunks)} chunks")
        all_chunks.extend(chunks)

    print(f"Total chunks: {len(all_chunks)}")
    if dry_run:
        courses = sorted({c.course for c in all_chunks})
        print("Courses:", ", ".join(courses))
        print("Dry run — no embeddings / upsert.")
        return

    if not env("PINECONE_API_KEY") or not env("OPENAI_API_KEY"):
        raise SystemExit(
            "Missing keys. Set PINECONE_API_KEY and OPENAI_API_KEY in the repo .env, then re-run."
        )

    pc = get_pinecone()
    index_name = ensure_index(pc)
    print(f"Pinecone index: {index_name}")
    print(f"Namespace: {env('PINECONE_NAMESPACE', DEFAULT_NAMESPACE)}")

    texts = [c.text for c in all_chunks]
    t0 = time.time()
    vectors = embed_texts(texts)
    print(f"Embedded {len(vectors)} chunks in {time.time() - t0:.1f}s")

    t1 = time.time()
    upserted = upsert_chunks(all_chunks, vectors)
    print(f"Upserted {upserted} vectors in {time.time() - t1:.1f}s")
    print("Done. Query with: py query.py \"your question\"")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest course PDFs into Pinecone")
    parser.add_argument("--pdf-root", type=Path, default=DEFAULT_PDF_ROOT)
    parser.add_argument(
        "--layout",
        default=PREFERRED_SLIDE_LAYOUT,
        help="1pp (default), 2pp, or all",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process only first N PDFs")
    parser.add_argument("--dry-run", action="store_true", help="Extract/chunk only, no upsert")
    args = parser.parse_args()
    ingest(args.pdf_root, args.layout, args.limit, args.dry_run)


if __name__ == "__main__":
    main()
