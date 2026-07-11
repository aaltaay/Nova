"""Tunables for Warrior Trading course PDF → Pinecone memory."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PDF_ROOT = REPO_ROOT / "downloads" / "warrior-trading-slides"

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


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()
