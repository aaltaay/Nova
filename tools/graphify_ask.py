#!/usr/bin/env python3
"""Run Graphify query/path/explain and record the token-savings meter.

Agents MUST use this wrapper, not a bare `graphify query`. The footer is the
keep/kill signal: if total_saved stays 0, delete Graphify.

Usage:
  py -3 tools/graphify_ask.py query "What connects Gap and Go to IBKR gates?"
  py -3 tools/graphify_ask.py path "Gap and Go Setup" "IBKR Safety Gates"
  py -3 tools/graphify_ask.py explain "Nova OS Decision Brain"
  py -3 tools/graphify_ask.py status
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from graphify_usage import (
    DEFAULT_STORE,
    format_footer,
    format_status,
    load_usage,
    record_event,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _graphify_bin() -> str:
    found = shutil.which("graphify")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "graphify.exe"
    if fallback.is_file():
        return str(fallback)
    raise SystemExit(
        "graphify CLI not found. Install: uv tool install graphifyy "
        "and keep %USERPROFILE%\\.local\\bin on PATH."
    )


def _run(args: list[str]) -> str:
    proc = subprocess.run(
        [_graphify_bin(), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.stderr:
        sys.stderr.write(proc.stderr)
        if not proc.stderr.endswith("\n"):
            sys.stderr.write("\n")
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout or "")
        raise SystemExit(proc.returncode)
    return proc.stdout or ""


def _emit(command: str, question: str, stdout: str) -> int:
    event = record_event(command=command, question=question, stdout=stdout)
    totals = load_usage(DEFAULT_STORE)
    sys.stdout.write(stdout)
    if stdout and not stdout.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.write(f"\n{format_footer(event, totals)}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Graphify query wrapper with savings meter")
    sub = parser.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("query", help="BFS/DFS question against graph.json")
    q.add_argument("question")
    q.add_argument("--dfs", action="store_true")
    q.add_argument("--budget", type=int, default=0)

    p = sub.add_parser("path", help="Shortest path between two nodes")
    p.add_argument("node_a")
    p.add_argument("node_b")

    e = sub.add_parser("explain", help="Explain one node and its neighbors")
    e.add_argument("node")

    sub.add_parser("status", help="Print cumulative savings meter")

    args = parser.parse_args(argv)
    if args.cmd == "status":
        sys.stdout.write(format_status(load_usage(DEFAULT_STORE)) + "\n")
        return 0

    extra: list[str] = []
    if args.cmd == "query":
        extra = ["query", args.question]
        if args.dfs:
            extra.append("--dfs")
        if args.budget:
            extra.extend(["--budget", str(args.budget)])
        question = args.question
    elif args.cmd == "path":
        extra = ["path", args.node_a, args.node_b]
        question = f"{args.node_a} -> {args.node_b}"
    else:
        extra = ["explain", args.node]
        question = args.node

    return _emit(args.cmd, question, _run(extra))


if __name__ == "__main__":
    raise SystemExit(main())
