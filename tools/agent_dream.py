#!/usr/bin/env python3
"""Nova agent dreaming — fleet memory consolidation (light / REM / deep).

Dry-run by default. Full mission flags:

  --write              apply agent + diary (+ optional surfaces below)
  --llm-rem / --no-llm-rem
  --obsidian           hygiene pass on 03-Nova-Decisions/
  --pinecone           course_memory ingest (dry-run unless --write)
  --pinecone-official  official caption transcripts
  --pinecone-full      no --limit on ingest
  --bridges            Claude Code autoDreamEnabled + OpenClaw MEMORY export
  --commit / --push    ship dream artifacts (requires --write)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# Windows consoles often use cp1252 — keep dream reports printable.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
except Exception:
    pass

from agent_dream_lib.phases import report_text, run_dream  # noqa: E402

REGISTRY_PATH = REPO_ROOT / ".cursor" / "agent-system" / "registry.json"
DIARY_PATH = REPO_ROOT / ".cursor" / "agent-system" / "DREAMS.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nova agent memory dreaming")
    parser.add_argument("--agent", default="all", help="Agent id or 'all'")
    parser.add_argument(
        "--phase",
        default="all",
        choices=["light", "rem", "deep", "all"],
    )
    parser.add_argument("--write", action="store_true", help="Apply mutations")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--diary", type=Path, default=DIARY_PATH)
    parser.add_argument(
        "--llm-rem",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="LLM REM diary when OPENAI_API_KEY is set (default: on)",
    )
    parser.add_argument(
        "--obsidian",
        action="store_true",
        help="Hygiene + stamp strategy notes under 03-Nova-Decisions/",
    )
    parser.add_argument(
        "--pinecone",
        action="store_true",
        help="Run tools/course_memory/ingest.py (dry-run unless --write)",
    )
    parser.add_argument(
        "--pinecone-official",
        action="store_true",
        help="With --pinecone, ingest official transcripts",
    )
    parser.add_argument(
        "--pinecone-full",
        action="store_true",
        help="With --pinecone, do not pass --limit",
    )
    parser.add_argument(
        "--bridges",
        action="store_true",
        help="Enable Claude Code autoDream + export OpenClaw MEMORY.md",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="git add/commit dream artifacts (requires --write)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="git push after --commit",
    )
    parser.add_argument(
        "--full-mission",
        action="store_true",
        help="Shorthand: --obsidian --pinecone --bridges (still dry-run unless --write)",
    )
    args = parser.parse_args(argv)

    if args.full_mission:
        args.obsidian = True
        args.pinecone = True
        args.bridges = True

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    try:
        report = run_dream(
            registry,
            REPO_ROOT,
            agent_filter=args.agent,
            phase=args.phase,
            write=args.write,
            diary_path=args.diary,
            llm_rem=args.llm_rem,
            obsidian=args.obsidian,
            pinecone=args.pinecone,
            pinecone_official=args.pinecone_official,
            pinecone_full=args.pinecone_full,
            bridges=args.bridges,
            commit=args.commit,
            push=args.push,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report_text(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
