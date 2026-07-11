"""Tunables for Warrior Trading course PDF → Pinecone memory."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PDF_ROOT = REPO_ROOT / "downloads" / "warrior-trading-slides"
DEFAULT_MARKDOWN_ROOT = REPO_ROOT / "knowledge" / "obsidian" / "01-Courses" / "Warrior-Trading"
DEFAULT_CAPTION_EXPORT_ROOT = REPO_ROOT / "downloads" / "warrior-trading-caption-notes"
# Only these frontmatter `source` values are safe to index into Pinecone by default.
OFFICIAL_TRANSCRIPT_SOURCES = ("warrior-trading-official-captions",)
# Old / inaccurate caption-note sources that must be purged before re-ingest.
STALE_CAPTION_SOURCES = (
    "warrior-trading-caption-notes",
)

# Prefer 1-slide-per-page PDFs (same content as 2pp, cleaner OCR/layout).
PREFERRED_SLIDE_LAYOUT = "1pp"

# Chunking — sized for accurate strategy recall without drowning the query.
CHUNK_MAX_CHARS = 1800
CHUNK_OVERLAP_CHARS = 250
MIN_CHUNK_CHARS = 80

# Embeddings (OpenAI)
DEFAULT_EMBED_MODEL = "text-embedding-3-small"
EMBED_DIMENSIONS = 1536
EMBED_BATCH_SIZE = 64

# Pinecone
DEFAULT_INDEX_NAME = "nova-warrior-courses"
DEFAULT_NAMESPACE = "warrior-slides"
PINECONE_CLOUD = "aws"
PINECONE_REGION = "us-east-1"
UPSERT_BATCH_SIZE = 50

# Query defaults
DEFAULT_TOP_K = 8

# Grounded Q&A (ask.py) — answer ONLY from retrieved course material.
ASK_MODEL = "gpt-4o-mini"
ASK_TOP_K = 12
ASK_OBSIDIAN_LIMIT = 4
ASK_MAX_CONTEXT_CHARS = 24_000
ASK_NO_ANSWER_TEXT = "NOT_IN_KNOWLEDGE_BASE"


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()
