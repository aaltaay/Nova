"""Audit Pinecone contents: report vector counts per source, flag stale sources."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

from constants import DEFAULT_NAMESPACE, REPO_ROOT, STALE_CAPTION_SOURCES, env
from embed import embed_texts
from pinecone_store import get_index

PROBE_QUERIES = [
    "loss control simulator buying power",
    "break of VWAP setup entry",
    "gap and go premarket high",
    "candlestick pullback pattern volume",
    "risk management max loss",
]


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    index = get_index()
    namespace = env("PINECONE_NAMESPACE", DEFAULT_NAMESPACE) or DEFAULT_NAMESPACE

    stats = index.describe_index_stats()
    ns_stats = (stats.get("namespaces") or {}).get(namespace, {})
    print(f"Namespace '{namespace}': {ns_stats.get('vector_count', '?')} total vectors")

    vectors = embed_texts(PROBE_QUERIES)
    seen_sources: dict[str, int] = {}
    stale_hits = []
    for query, vector in zip(PROBE_QUERIES, vectors):
        result = index.query(
            vector=vector, top_k=25, include_metadata=True, namespace=namespace
        )
        for match in result.get("matches", []) or []:
            source = (match.get("metadata") or {}).get("source", "<missing>")
            seen_sources[source] = seen_sources.get(source, 0) + 1
            if source in STALE_CAPTION_SOURCES:
                stale_hits.append((query, match.get("id")))

    print("\nSources seen across probe queries (top-25 each):")
    for source, count in sorted(seen_sources.items(), key=lambda kv: -kv[1]):
        print(f"  {source}: {count}")

    # Direct check: query filtered to stale sources must return nothing.
    for source in STALE_CAPTION_SOURCES:
        result = index.query(
            vector=vectors[0],
            top_k=5,
            namespace=namespace,
            filter={"source": {"$eq": source}},
        )
        remaining = len(result.get("matches", []) or [])
        status = "OK — purged" if remaining == 0 else f"FAIL — {remaining} vectors remain"
        print(f"\nStale source '{source}': {status}")

    if stale_hits:
        print("\nFAIL: stale vectors surfaced in probe queries:")
        for query, vec_id in stale_hits:
            print(f"  {query} -> {vec_id}")
        raise SystemExit(1)
    print("\nPASS: no stale caption-note vectors surfaced.")


if __name__ == "__main__":
    main()
