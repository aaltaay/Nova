"""OpenAI embeddings for course chunks."""

from __future__ import annotations

from openai import OpenAI

from constants import DEFAULT_EMBED_MODEL, EMBED_BATCH_SIZE, EMBED_DIMENSIONS, env


def get_openai_client() -> OpenAI:
    api_key = env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for embeddings.")
    return OpenAI(api_key=api_key)


def embed_texts(texts: list[str], model: str | None = None) -> list[list[float]]:
    if not texts:
        return []
    client = get_openai_client()
    model = model or env("OPENAI_EMBEDDING_MODEL", DEFAULT_EMBED_MODEL) or DEFAULT_EMBED_MODEL
    vectors: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        response = client.embeddings.create(model=model, input=batch, dimensions=EMBED_DIMENSIONS)
        # API returns in order of input index
        ordered = sorted(response.data, key=lambda row: row.index)
        vectors.extend([row.embedding for row in ordered])
    return vectors
