"""Pinecone index helpers for course memory."""

from __future__ import annotations

from pinecone import Pinecone, ServerlessSpec

from constants import (
    DEFAULT_INDEX_NAME,
    DEFAULT_NAMESPACE,
    EMBED_DIMENSIONS,
    PINECONE_CLOUD,
    PINECONE_REGION,
    UPSERT_BATCH_SIZE,
    env,
)
from chunk import Chunk


def get_pinecone() -> Pinecone:
    api_key = env("PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("PINECONE_API_KEY is required.")
    return Pinecone(api_key=api_key)


def ensure_index(pc: Pinecone | None = None, name: str | None = None) -> str:
    pc = pc or get_pinecone()
    name = name or env("PINECONE_INDEX", DEFAULT_INDEX_NAME) or DEFAULT_INDEX_NAME
    existing = {idx["name"] for idx in pc.list_indexes()}
    if name not in existing:
        pc.create_index(
            name=name,
            dimension=EMBED_DIMENSIONS,
            metric="cosine",
            spec=ServerlessSpec(
                cloud=env("PINECONE_CLOUD", PINECONE_CLOUD) or PINECONE_CLOUD,
                region=env("PINECONE_REGION", PINECONE_REGION) or PINECONE_REGION,
            ),
        )
    return name


def get_index(pc: Pinecone | None = None, name: str | None = None):
    pc = pc or get_pinecone()
    name = ensure_index(pc, name)
    host = env("PINECONE_HOST")
    if host:
        return pc.Index(name, host=host)
    return pc.Index(name)


def chunk_to_record(chunk: Chunk, values: list[float]) -> dict:
    # Prefix text into metadata for grounded answers (Pinecone metadata size limits apply).
    preview = chunk.text if len(chunk.text) <= 3500 else chunk.text[:3490] + "…"
    return {
        "id": chunk.id,
        "values": values,
        "metadata": {
            "text": preview,
            "course": chunk.course,
            "chapter": chunk.chapter,
            "filename": chunk.filename,
            "layout": chunk.layout,
            "page": chunk.page,
            "chunk_index": chunk.chunk_index,
            "rel_path": chunk.rel_path,
            "source": chunk.source,
            "unit": chunk.unit,
            "timestamp_start": chunk.timestamp_start,
        },
    }


def delete_by_source(
    sources: list[str],
    namespace: str | None = None,
) -> None:
    """Remove vectors whose metadata.source is in ``sources`` (exact match)."""
    if not sources:
        return
    index = get_index()
    namespace = namespace or env("PINECONE_NAMESPACE", DEFAULT_NAMESPACE) or DEFAULT_NAMESPACE
    for source in sources:
        index.delete(filter={"source": {"$eq": source}}, namespace=namespace)


def upsert_chunks(
    chunks: list[Chunk],
    vectors: list[list[float]],
    namespace: str | None = None,
) -> int:
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors length mismatch")
    index = get_index()
    namespace = namespace or env("PINECONE_NAMESPACE", DEFAULT_NAMESPACE) or DEFAULT_NAMESPACE
    total = 0
    batch: list[dict] = []
    for chunk, values in zip(chunks, vectors):
        batch.append(chunk_to_record(chunk, values))
        if len(batch) >= UPSERT_BATCH_SIZE:
            index.upsert(vectors=batch, namespace=namespace)
            total += len(batch)
            batch = []
    if batch:
        index.upsert(vectors=batch, namespace=namespace)
        total += len(batch)
    return total


def query_memory(
    vector: list[float],
    top_k: int = 8,
    namespace: str | None = None,
    course_contains: str | None = None,
) -> list[dict]:
    index = get_index()
    namespace = namespace or env("PINECONE_NAMESPACE", DEFAULT_NAMESPACE) or DEFAULT_NAMESPACE
    kwargs: dict = {
        "vector": vector,
        "top_k": top_k,
        "include_metadata": True,
        "namespace": namespace,
    }
    if course_contains:
        kwargs["filter"] = {"course": {"$eq": course_contains}}
    result = index.query(**kwargs)
    matches = []
    for match in result.get("matches", []) or []:
        meta = match.get("metadata") or {}
        matches.append(
            {
                "id": match.get("id"),
                "score": match.get("score"),
                "text": meta.get("text", ""),
                "course": meta.get("course", ""),
                "chapter": meta.get("chapter", ""),
                "unit": meta.get("unit", ""),
                "page": meta.get("page"),
                "rel_path": meta.get("rel_path", ""),
                "source": meta.get("source", ""),
                "timestamp_start": meta.get("timestamp_start", ""),
            }
        )
    return matches
