#!/usr/bin/env python3
"""Nova backlog triage: what to work on next, and whether the board still says so.

The backlog is organised into **work packages**. A package is a coherent
outcome, not a module: "after this, recording cannot wedge the desk" rather
than "backend/capture". Every open issue belongs to exactly one.

Two homes, one direction of flow:

  ``knowledge/backlog-packages.json``  AUTHORED. Rank, objective, definition
      of done, and which issues batch into which pull request.
  **GitHub milestones**                PROJECTED from that file by ``sync``.
      First-class in the REST/GraphQL API and in issue search
      (``milestone:"01 - ..."``), so a bot that is not Claude Code -- an
      Action, a dashboard, a webhook, ``gh`` in a shell -- reads the plan
      without parsing Markdown.

Issue *state* (open/closed, labels) always comes from GitHub and never from
the JSON, so a stale file degrades a listing but cannot resurrect closed work.
``check`` reports drift between the two; nothing here self-heals.

The agent entry point is ``next``: it prints one package, one pull request,
and the acceptance criteria, so a fresh session can start without reading the
whole backlog.

This module is the CLI. The work lives in backlog_github / backlog_plan /
backlog_claims / backlog_render, split so no file exceeds the 400-line limit
in AGENTS.md 2.3. The names below are re-exported so existing callers and
``from tools.backlog_triage import ...`` keep working.

Usage:
  python3 tools/backlog_triage.py next              # <- "what do I work on?"
  python3 tools/backlog_triage.py next --package <slug>
  python3 tools/backlog_triage.py triage            # <- route the inbox
  python3 tools/backlog_triage.py claims            # <- who holds what
  python3 tools/backlog_triage.py claim --package recorder-safety
  python3 tools/backlog_triage.py release --package recorder-safety
  python3 tools/backlog_triage.py report [--json]
  python3 tools/backlog_triage.py check             # exit 1 on gaps or drift
  python3 tools/backlog_triage.py sync [--dry-run]  # packages -> milestones
  python3 tools/backlog_triage.py sync-map --issue NNN
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Invoked as `py -3 tools/backlog_triage.py`, sys.path[0] is tools/, so the
# `tools.*` imports below would not resolve. Put the repo root first.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.backlog_claims import (  # noqa: F401  (re-exported)
    CLAIM_BEGIN,
    CLAIM_END,
    CLAIM_LABEL,
    CLAIM_RELEASE,
    CLAIM_TTL_HOURS,
    active_claim,
    agent_id,
    batch_ref,
    format_claim,
    format_release,
    live_claims,
    parse_claim,
    resolve_batch,
    stale_claims,
)
from tools.backlog_github import (  # noqa: F401  (re-exported)
    DEFAULT_REPO,
    EXIT_ERROR,
    EXIT_GAPS,
    EXIT_OK,
    INBOX_TITLE,
    KINDS,
    META_LABEL,
    NO_MILESTONE,
    SEVERITIES,
    URGENT,
    Runner,
    domain_labels,
    fetch_comments,
    fetch_issues,
    fetch_milestones,
    is_meta,
    label_names,
    milestone_title,
    repo_slug,
    run_gh,
    severity_of,
)
from tools.backlog_plan import (  # noqa: F401  (re-exported)
    PACKAGES_PATH,
    READY,
    REPO_ROOT,
    analyse,
    candidate_packages,
    duplicate_aliases,
    hygiene_gaps,
    load_packages,
    milestone_description,
    next_pr,
    pick_next,
    plan_drift,
    rollup,
    with_inbox,
)
from tools.backlog_render import (  # noqa: F401  (re-exported)
    MAP_BEGIN,
    MAP_END,
    render_map_section,
    render_next,
    render_report,
    render_triage,
    splice_map,
)


from tools.backlog_commands import (
    cmd_check,
    cmd_claim,
    cmd_claims,
    cmd_next,
    cmd_release,
    cmd_report,
    cmd_sync,
    cmd_sync_map,
    cmd_triage,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nova backlog triage (packages, milestones, labels)")
    sub = parser.add_subparsers(dest="command", required=True)

    nxt = sub.add_parser("next", help="the one package and PR to start now")
    nxt.add_argument("--json", action="store_true")
    nxt.add_argument("--package", default=None,
                     help="report this package's live state instead of the auto-picked one")
    nxt.set_defaults(func=cmd_next)

    clm = sub.add_parser("claims", help="who is holding which batch")
    clm.add_argument("--conflicts", action="store_true", help="show batches blocked by held files")
    clm.set_defaults(func=cmd_claims)

    cla = sub.add_parser("claim", help="claim a PR batch before working it")
    cla.add_argument("--package", required=True, help="package slug")
    cla.add_argument("--batch", type=int, default=None, help="batch index (default 0)")
    cla.add_argument("--agent", default=None, help="agent id (default $NOVA_AGENT_ID)")
    cla.add_argument("--branch", default=None,
                     help="branch to cut and link (default agent/<slug>-<batch>)")
    cla.add_argument("--force", action="store_true", help="take over a stale claim")
    cla.set_defaults(func=cmd_claim)

    rel = sub.add_parser("release", help="release a batch you claimed")
    rel.add_argument("--package", required=True)
    rel.add_argument("--batch", type=int, default=None)
    rel.add_argument("--agent", default=None)
    rel.add_argument("--branch", default=None,
                     help="branch to clean up (default: the one the claim recorded)")
    rel.add_argument("--keep-branch", action="store_true",
                     help="release the claim but leave the branch on origin")
    rel.set_defaults(func=cmd_release)

    tri = sub.add_parser("triage", help="list inbox issues with routing context")
    tri.add_argument("--json", action="store_true")
    tri.set_defaults(func=cmd_triage)

    rep = sub.add_parser("report", help="package rollup, hygiene gaps and plan drift")
    rep.add_argument("--json", action="store_true")
    rep.set_defaults(func=cmd_report)

    chk = sub.add_parser("check", help="same as report, but exit 1 on gaps or drift")
    chk.set_defaults(func=cmd_check)

    syn = sub.add_parser("sync", help="project packages onto milestones and issue assignments")
    syn.add_argument("--dry-run", action="store_true")
    syn.set_defaults(func=cmd_sync)

    smap = sub.add_parser("sync-map", help="refresh the generated block in the Backlog Map issue")
    smap.add_argument("--issue", type=int, required=True)
    smap.add_argument("--dry-run", action="store_true")
    smap.set_defaults(func=cmd_sync_map)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
