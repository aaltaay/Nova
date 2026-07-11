"""Query Pinecone course memory and print grounded snippets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

from constants import DEFAULT_TOP_K, REPO_ROOT
from embed import embed_texts
from pinecone_store import query_memory


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Query Warrior course memory in Pinecone")
    parser.add_argument("question", nargs="+", help="Natural language question")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--course", default=None, help="Exact course folder name filter")
    parser.add_argument("--json", action="store_true", help="Print raw JSON matches")
    args = parser.parse_args()

    question = " ".join(args.question).strip()
    vector = embed_texts([question])[0]
    matches = query_memory(vector, top_k=args.top_k, course_contains=args.course)

    if args.json:
        print(json.dumps(matches, indent=2))
        return

    print(f"Q: {question}\n")
    if not matches:
        print("No matches.")
        return
    for i, m in enumerate(matches, start=1):
        print(f"--- [{i}] score={m['score']:.4f} | {m['course']} / {m['chapter']} p{m['page']} ---")
        print(m["text"])
        print(f"source: {m['rel_path']}\n")


if __name__ == "__main__":
    main()
