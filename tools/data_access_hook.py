#!/usr/bin/env python3
"""Tripwire: an agent reads the operator's raw market data through the front door, not its own reader (ADR 059).

Wired as a Cursor ``beforeShellExecution`` hook and a Claude Code ``PreToolUse`` hook on Bash. It denies a shell
command, inline Python or ad-hoc script that names a raw store -- the Massive files and reference dump, the day
movers and leaderboard SQLite stores, SEC's bulk zips -- pointing at ``tools/market_data.py`` and the ``nova-data``
MCP server instead. Code in this repo (``backend/``, ``research/``, ``tools/``) is reviewed and gated, so running it
passes; a script outside the repo is read and checked. A command may say why it must go raw with
``# raw-data-ok: <reason>``. A tripwire, not a wall: any parse failure allows. File reads are not hooked: a Python
start on every read cost ~370 ms, and the stores are gzip and SQLite, which a read tool cannot use.

  py -3 tools/data_access_hook.py --client cursor-shell|claude   (hook JSON on stdin, verdict on stdout)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FOLDERS = ("nova/massive", "nova/leaderboard", "catalysts/edgar")
MARKERS = (*FOLDERS, "store/reference", "day_movers.sqlite3", "leaderboard.sqlite3", "reference_index.sqlite3",
           "companyfacts.zip", "submissions.zip", "minute_aggs_v1", "trades_v1", "quotes_v1")
# A code search or git names a store's file name as a pattern; it reads raw data only when pointed at a data folder.
SEARCHES = ("rg", "grep", "git", "gh", "findstr", "select-string")
FRONT_DOOR = ("tools/market_data.py", "tools/nova_data_mcp.py", "tools/nova_mcp.py", "tools/nova_review_load.py",
              "tools/nova_agent.py", "tools/nova_charts.py", "tools/nova_historical_charts.py")
OVERRIDE = "raw-data-ok:"
SCRIPT = re.compile(r"""(?:^|[\s"'])((?:[A-Za-z]:)?[^\s"']+\.py)\b""")
MAX_SCRIPT_BYTES = 2_000_000
MESSAGE = ("Raw Nova market data goes through the front door: `py -3 tools/market_data.py catalog` lists every "
           "dataset (trades, quotes, bars, movers, boards, splits, financials, SEC shares/filings, float, IPOs, short "
           "interest) and the call that reads it; agents can use the nova-data MCP tools. They carry the units and "
           "as-of rules a private reader gets wrong (docs/market-data.md, ADR 059). If a read truly needs the raw "
           "files, add `# raw-data-ok: <reason>` to the command.")


def _norm(text: str) -> str:
    return text.replace("\\", "/").lower()


def names_raw_store(text: str) -> bool:
    norm = _norm(text)
    return any(marker in norm for marker in MARKERS)


def _in_repo(path: Path) -> bool:
    try:
        return path.resolve().is_relative_to(REPO.resolve())
    except (OSError, ValueError):
        return False


def shell_verdict(command: str, cwd: str | None = None) -> str | None:
    """The reason to deny ``command``, else None."""
    norm = _norm(command)
    if OVERRIDE in norm or any(door in norm for door in FRONT_DOOR):
        return None
    first = norm.split(maxsplit=1)[0] if norm.strip() else ""
    if first in SEARCHES:
        return "the search reads a raw data folder" if any(f in norm for f in FOLDERS) else None
    if names_raw_store(command):
        return "the command names a raw data store"
    for match in SCRIPT.finditer(command):
        path = Path(match.group(1))
        if not path.is_absolute() and cwd:
            path = Path(cwd) / path
        if _in_repo(path) or not path.is_file() or path.stat().st_size > MAX_SCRIPT_BYTES:
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if OVERRIDE not in _norm(body) and names_raw_store(body):
            return f"the script {path.name} (outside the repo) reads a raw data store"
    return None


def decide(client: str, payload: dict) -> dict:
    if client == "cursor-shell":
        reason = shell_verdict(str(payload.get("command") or ""), payload.get("cwd"))
    else:
        args = payload.get("tool_input") or {}
        reason = shell_verdict(str(args.get("command") or ""), payload.get("cwd")) \
            if payload.get("tool_name") == "Bash" else None
    if client.startswith("cursor"):
        if not reason:
            return {"permission": "allow"}
        return {"permission": "deny", "user_message": f"Blocked a raw data read: {reason}.",
                "agent_message": f"Blocked: {reason}. {MESSAGE}"}
    if not reason:
        return {}
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": f"Blocked: {reason}. {MESSAGE}"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--client", required=True, choices=["cursor-shell", "claude"])
    args = parser.parse_args(argv)
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        verdict = decide(args.client, payload if isinstance(payload, dict) else {})
    except Exception:  # maintainer: allow-swallow a tripwire that cannot parse its input allows (fail open)
        verdict = {"permission": "allow"} if args.client.startswith("cursor") else {}
    if verdict:
        sys.stdout.write(json.dumps(verdict))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
