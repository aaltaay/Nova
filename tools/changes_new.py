#!/usr/bin/env python3
"""Scaffold a ledger fragment for work that has no pull request.

Most work does NOT need this. `CHANGELOG.md` is generated from merged PR
bodies (AGENTS.md 7.1), so a normal PR carries its entry in its own body and
writes nothing here.

Use this only when there is no PR to derive from: a direct push, an ops
diagnosis, an audit conclusion. The fragment is a new file with a unique name,
so it cannot conflict with another agent's; `changes_collate.py` folds it into
the ledger and deletes it.

Usage:
  python3 tools/changes_new.py --kind fix --scope capture \\
      --title "Recorder stop no longer deadlocks"
  python3 tools/changes_new.py --kind chore --scope ops --problem \\
      --title "Gateway wedged on reqCompletedOrders"
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.changes_fragments import (  # noqa: E402
    CHANGES_DIR,
    KINDS,
    PROBLEMS_DIR,
    fragment_name,
    render_fragment,
    slugify,
)

CHANGE_TEMPLATE = """- **What:** <1-2 sentences on what changed>
- **Why:** <trigger: user request, bug class, cleanup>
- **How it works now:** <the mental model a future agent needs>
- **Verified by:** <command run and its actual result>"""

PROBLEM_TEMPLATE = """- **Symptom:** <what was observed>
- **Cause:** <the actual root cause, not the symptom>
- **Fix:** <what changed>
- **Keywords:** <terms a future search would use>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a ledger fragment (no-PR work only)")
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--scope", default="", help="module or area, e.g. capture")
    parser.add_argument("--title", required=True)
    parser.add_argument("--pr", default="", help="PR number, if one exists after all")
    parser.add_argument("--problem", action="store_true",
                        help="write a PROBLEM_LOG fragment instead of a CHANGELOG one")
    parser.add_argument("--slug", default=None, help="override the filename slug")
    args = parser.parse_args(argv)

    slug = args.slug or slugify(args.title)
    if not slug:
        print("--title produced an empty slug; pass --slug", file=sys.stderr)
        return 1

    # Second resolution: two agents scaffolding in the same minute would
    # otherwise land on the same filename and reintroduce the conflict this
    # whole mechanism exists to remove.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    directory = PROBLEMS_DIR if args.problem else CHANGES_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / fragment_name(stamp, slug)

    path.write_text(
        render_fragment(
            kind=args.kind,
            scope=args.scope,
            pr=args.pr,
            title=args.title,
            body=PROBLEM_TEMPLATE if args.problem else CHANGE_TEMPLATE,
        ),
        encoding="utf-8",
    )
    print(f"Created {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")
    print("Fill in the body, commit it, and the collation job folds it in on master.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
