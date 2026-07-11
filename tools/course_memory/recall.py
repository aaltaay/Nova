"""
Unified recall: route questions to Obsidian, Pinecone, or both.

You ask in plain English. This script chooses the store(s).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

from constants import DEFAULT_TOP_K, REPO_ROOT, env
from obsidian_store import search_obsidian

# Decision / product intent → Obsidian primary
_OBSIDIAN_HINTS = re.compile(
    r"\b(nova|automat|build|roadmap|decid|we chose|our (plan|choice)|prefer|"
    r"should i (build|code|implement)|ibkr|paper trade|active strategy|"
    r"candidate strateg|what did we)\b",
    re.I,
)

# Course / curriculum intent → Pinecone primary
_PINECONE_HINTS = re.compile(
    r"\b(course|chapter|ross|warrior|slide|pdf|gap\s*and\s*go|abcd|hod|"
    r"vwap|float|relative volume|rvol|premarket|entry|exit|stop loss|"
    r"risk (rule|management)|setup|pattern|scalp|psychology|lesson)\b",
    re.I,
)


def _configure_utf8_console() -> None:
    """Allow arbitrary note text to print safely in Windows terminals."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def choose_source(question: str, forced: str | None) -> str:
    if forced in {"obsidian", "pinecone", "both"}:
        return forced
    o = bool(_OBSIDIAN_HINTS.search(question))
    p = bool(_PINECONE_HINTS.search(question))
    if o and p:
        return "both"
    if o:
        return "obsidian"
    if p:
        return "pinecone"
    return "both"  # ambiguous → both


def recall_pinecone(question: str, top_k: int, course: str | None) -> list[dict]:
    if not env("PINECONE_API_KEY") or not env("OPENAI_API_KEY"):
        return [
            {
                "error": "Pinecone/OpenAI keys missing in .env — run ingest after adding keys.",
                "score": 0,
            }
        ]
    try:
        from embed import embed_texts
        from pinecone_store import query_memory

        vector = embed_texts([question])[0]
        return query_memory(vector, top_k=top_k, course_contains=course)
    except Exception as exc:  # noqa: BLE001 — surface to user clearly
        return [{"error": str(exc), "score": 0}]


def format_pinecone_match(match: dict, index: int) -> str:
    location = f"p{match.get('page')}"
    if match.get("timestamp_start"):
        location = f"@ {match['timestamp_start']}"
    return "\n".join(
        [
            (
                f"[{index}] score={match.get('score', 0):.4f} | "
                f"{match.get('course')} / {match.get('chapter')} {location}"
            ),
            match.get("text", ""),
            f"source: {match.get('source')} | {match.get('rel_path')}",
        ]
    )


def main() -> None:
    _configure_utf8_console()
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Recall from Obsidian and/or Pinecone")
    parser.add_argument("question", nargs="+")
    parser.add_argument("--source", choices=["auto", "obsidian", "pinecone", "both"], default="auto")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--course", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    question = " ".join(args.question).strip()
    forced = None if args.source == "auto" else args.source
    source = choose_source(question, forced)

    payload: dict = {"question": question, "source": source, "obsidian": [], "pinecone": []}

    if source in {"obsidian", "both"}:
        hits = search_obsidian(question, limit=args.top_k)
        payload["obsidian"] = [
            {"title": h.title, "path": h.path, "score": h.score, "snippet": h.snippet, "folder": h.folder}
            for h in hits
        ]

    if source in {"pinecone", "both"}:
        payload["pinecone"] = recall_pinecone(question, args.top_k, args.course)

    if args.json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Q: {question}")
    print(f"Router -> {source}\n")

    if payload["obsidian"]:
        print("=== OBSIDIAN (curated decisions / Nova) ===")
        for i, h in enumerate(payload["obsidian"], 1):
            print(f"[{i}] {h['title']}  ({h['path']})  score={h['score']:.1f}")
            print(h["snippet"])
            print()
    elif source in {"obsidian", "both"}:
        print("=== OBSIDIAN ===\n(no note hits)\n")

    if payload["pinecone"]:
        print("=== PINECONE (course materials) ===")
        for i, m in enumerate(payload["pinecone"], 1):
            if m.get("error"):
                print(f"[{i}] {m['error']}\n")
                continue
            print(f"{format_pinecone_match(m, i)}\n")
    elif source in {"pinecone", "both"}:
        print("=== PINECONE ===\n(no matches)\n")

    print(
        "Trust order: Obsidian decisions > Pinecone citations > model guesses. "
        "Update knowledge/obsidian/03-Nova-Decisions/ when you decide."
    )


if __name__ == "__main__":
    main()
