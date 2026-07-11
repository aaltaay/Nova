"""Grounded Q&A CLI: answer questions ONLY from the course knowledge base.

Flow: route question -> retrieve from Pinecone (slides + official captions)
and Obsidian -> hand the retrieved chunks to the model with a strict
"context-only" prompt -> print the answer with numbered citations.

The model is forbidden from using outside knowledge. If the retrieved
material does not contain the answer, it must say so instead of guessing.

Usage:
    py ask.py "How do we leverage Level 2?"
    py ask.py --show-sources "What is the gap and go setup?"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

from constants import (
    ASK_MAX_CONTEXT_CHARS,
    ASK_MODEL,
    ASK_NO_ANSWER_TEXT,
    ASK_OBSIDIAN_LIMIT,
    ASK_TOP_K,
    REPO_ROOT,
    env,
)
from embed import get_openai_client
from obsidian_store import search_obsidian
from recall import _configure_utf8_console, choose_source, recall_pinecone

_SYSTEM_PROMPT = f"""You answer questions using ONLY the numbered context blocks provided.

Hard rules:
1. Every claim in your answer must come from the context blocks. Cite the block
   number(s) like [3] after each claim.
2. Do NOT use outside knowledge, general trading knowledge, or guesses — even if
   you know the answer. Context blocks are the only allowed source.
3. When a block has a video timestamp or slide page, include it in the citation.
4. If the context does not contain enough to answer, reply with exactly:
   {ASK_NO_ANSWER_TEXT}
   followed by one sentence naming what is missing.
Answer in clear prose, concise but complete."""


def gather_context(question: str) -> tuple[list[dict], str]:
    """Retrieve from both stores; return (source_records, numbered context text)."""
    records: list[dict] = []

    for match in recall_pinecone(question, ASK_TOP_K, course=None):
        if match.get("error") or not match.get("text"):
            continue
        where = f"p{match.get('page')}"
        if match.get("timestamp_start"):
            where = f"@ {match['timestamp_start']}"
        records.append(
            {
                "label": f"{match.get('course')} / {match.get('chapter')} {where}",
                "detail": f"{match.get('source')} | {match.get('rel_path')}",
                "text": match["text"],
            }
        )

    for hit in search_obsidian(question, limit=ASK_OBSIDIAN_LIMIT):
        records.append(
            {
                "label": f"Obsidian: {hit.title}",
                "detail": hit.path,
                "text": hit.snippet,
            }
        )

    blocks: list[str] = []
    used = 0
    kept: list[dict] = []
    for record in records:
        block = f"[{len(kept) + 1}] {record['label']}\n{record['text']}"
        if used + len(block) > ASK_MAX_CONTEXT_CHARS:
            break
        blocks.append(block)
        used += len(block)
        kept.append(record)
    return kept, "\n\n".join(blocks)


def ask(question: str) -> tuple[str, list[dict]]:
    records, context = gather_context(question)
    if not context:
        return f"{ASK_NO_ANSWER_TEXT} — retrieval returned nothing for this question.", []

    client = get_openai_client()
    model = env("OPENAI_ASK_MODEL", ASK_MODEL) or ASK_MODEL
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Context blocks:\n\n{context}\n\nQuestion: {question}",
            },
        ],
    )
    return (response.choices[0].message.content or "").strip(), records


def main() -> None:
    _configure_utf8_console()
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Ask the course knowledge base (grounded answers only)")
    parser.add_argument("question", nargs="+")
    parser.add_argument("--show-sources", action="store_true", help="Print every retrieved block")
    args = parser.parse_args()

    question = " ".join(args.question).strip()
    print(f"Q: {question}")
    print(f"Router -> {choose_source(question, None)}\n")

    answer, records = ask(question)
    print(answer)

    if records:
        print("\n--- Citations ---")
        for i, record in enumerate(records, 1):
            print(f"[{i}] {record['label']}  ({record['detail']})")
        if args.show_sources:
            print("\n--- Retrieved text ---")
            for i, record in enumerate(records, 1):
                print(f"\n[{i}] {record['label']}\n{record['text']}")


if __name__ == "__main__":
    main()
