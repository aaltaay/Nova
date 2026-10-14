#!/usr/bin/env python3
"""Say a held Release out loud: an issue while master's build is not on the update feed (operator report 2026-10-14).

v1297 (PR #947, merged 04:08 UTC) was held by its release checks -- a test that read the real clock, then a Market
page thread from another test -- and nothing but a red job in Actions said so. Eight hours later the operator asked
"How come I don't see these changes?". ``release_gate.py`` decides; this tool makes its "no" reach a person:

- ``open``: the gate held a master build. Open an issue titled ``Release held: vNNN ...`` (``bug``, ``P1``,
  ``domain:ci``), or comment on that tag's issue when a re-run is held again, so the next-move picks and the backlog
  name it as urgent.
- ``close``: a Release published. Every open ``Release held`` issue for that tag or an older one is closed: a vNNN
  Release carries every commit before it. A newer tag's issue stays open (runs can finish out of order).

Usage (the Desktop pack workflow's `Publish vNNN installer` job):
  python3 tools/release_held.py open --tag v1297 --sha <sha> --run-url <url> --summary-file gate.md
  python3 tools/release_held.py close --tag v1298
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

TITLE_PREFIX = "Release held:"
LABELS: tuple[str, ...] = ("bug", "P1", "domain:ci")

Runner = Callable[[list[str]], str]


def gh(args: list[str]) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def title(tag: str) -> str:
    return f"{TITLE_PREFIX} {tag} is not on the desk's update feed"


def body(tag: str, sha: str, run_url: str, summary: str) -> str:
    return "\n".join([
        f"The release checks held **{tag}** (`{sha[:12]}`), so the desk's update feed still offers the Release "
        "before it: nothing merged since then reaches the desk.",
        "",
        summary.strip() or "_The gate's summary was not written; see the run._",
        "",
        f"Run: {run_url}",
        "",
        "**Next:** fix what failed (a test that fails on master fails on every PR too), or, if it was a flake, "
        "**Re-run failed jobs** on the run. The next published Release closes this issue.",
    ]) + "\n"


def _revision(tag: str) -> int | None:
    found = re.fullmatch(r"v(\d+)", tag.strip())
    return int(found.group(1)) if found else None


def open_held(runner: Runner) -> dict[int, int]:
    """Open ``Release held`` issues: number -> the vNNN revision its title names."""
    out = runner(["issue", "list", "--state", "open", "--search", f'"{TITLE_PREFIX}" in:title',
                  "--json", "number,title", "--limit", "50"])
    held: dict[int, int] = {}
    for issue in json.loads(out or "[]"):
        found = re.match(re.escape(TITLE_PREFIX) + r" v(\d+)\b", str(issue.get("title", "")))
        if found:
            held[int(issue["number"])] = int(found.group(1))
    return held


def report(runner: Runner, tag: str, sha: str, run_url: str, summary: str) -> str:
    """Comment on this tag's open issue (a re-run held again), or open one; returns what was done."""
    text = body(tag, sha, run_url, summary)
    same = [n for n, rev in open_held(runner).items() if rev == _revision(tag)]
    if same:
        runner(["issue", "comment", str(same[0]), "--body", text])
        return f"commented on #{same[0]}"
    labels = [arg for label in LABELS for arg in ("--label", label)]
    return "opened " + runner(["issue", "create", "--title", title(tag), "--body", text, *labels]).strip()


def resolve(runner: Runner, tag: str) -> list[int]:
    """Close every open ``Release held`` issue for ``tag`` or an older tag; returns their numbers."""
    published = _revision(tag)
    if published is None:
        return []
    closed = [n for n, rev in open_held(runner).items() if rev <= published]
    for number in closed:
        runner(["issue", "close", str(number), "--reason", "completed", "--comment",
                f"{tag} published: it carries every commit before it, so the held build's changes are on the "
                "desk's update feed now."])
    return closed


def main(argv: list[str] | None = None, runner: Runner = gh) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    held = sub.add_parser("open", help="the gate held this master build")
    held.add_argument("--tag", required=True)
    held.add_argument("--sha", required=True)
    held.add_argument("--run-url", required=True)
    held.add_argument("--summary-file", type=Path)
    done = sub.add_parser("close", help="this tag published")
    done.add_argument("--tag", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "open":
        summary = ""
        if args.summary_file and args.summary_file.is_file():
            summary = args.summary_file.read_text(encoding="utf-8")
        print(report(runner, args.tag, args.sha, args.run_url, summary))
    else:
        print(f"closed {resolve(runner, args.tag) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
