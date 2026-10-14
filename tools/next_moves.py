#!/usr/bin/env python3
"""Next-move picks: fetch, rank, render, lint (AGENTS.md §5, next-move-footer.mdc).

Read-only. Every reply that ends a task offers the operator the best three next
moves, ranked from the live state (`next_move_picks`): red PRs, open P0/P1 bugs
including untriaged ones, the backlog's next batch, the inbox, the decision that
frees the most work and the roadmap's human steps. `card` prints the clickable
card for the Claude desktop app, `menu` the text menu for every other client,
`seed` the ranked list the session brief injects, `lint` checks a text menu. No
issue number, slug or PR title is ever recalled from memory.

Every GitHub call is bounded by SEED_TIMEOUT_SEC; a source that cannot be read
adds no picks rather than guessed ones.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.backlog_branches import last_commit_at  # noqa: E402
from tools.backlog_claims import CLAIM_LABEL, resolve_claim  # noqa: E402
from tools.backlog_github import (  # noqa: E402
    fetch_comments,
    fetch_issues,
    label_names,
    repo_slug,
    run_gh,
)
from tools.backlog_plan import load_packages, with_inbox  # noqa: E402
from tools.next_move_picks import (  # noqa: E402
    FORBIDDEN_PHRASES,
    PICKS_SHOWN,
    all_picks,
    apply_say,
    rank,
    thread_pick,
)
from tools.next_move_render import MENU_HEADING, render_card, render_menu, render_seed  # noqa: E402

ROADMAP_STATUS = (
    REPO_ROOT / "knowledge" / "obsidian" / "03-Nova-Decisions" / "Nova-Roadmap-Status.md"
)

# ---- footer contract (single home; AGENTS.md §5 and the .mdc cite these) ----
YOUR_CALL_HEADING = "**Your call**"
BETTER_ASK_LABEL = "**Better ask:**"
MIN_OPTIONS = 1
MAX_OPTIONS = PICKS_SHOWN
MAX_ANSWER_CHOICES = 5
OPTION_MAX_WORDS = 40
BETTER_ASK_MAX_WORDS = 35
FOOTER_MAX_WORDS = 280
SEED_LIMIT = 8
SEED_TIMEOUT_SEC = 8
PR_FIELDS = "number,title,isDraft,labels,mergeable,statusCheckRollup"


class _Budget:
    """Wall-clock budget shared by every gh call in one seed run."""

    def __init__(self, seconds: float) -> None:
        self.deadline = time.monotonic() + seconds

    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def run(self, cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        left = self.remaining()
        if left <= 0:
            raise TimeoutError("seed budget exhausted")
        kw["timeout"] = min(kw.get("timeout") or left, left)
        return subprocess.run(cmd, **kw)


def _branch_activity(budget: _Budget):
    """Branch lookup for staleness, on the seed's budget (claim-resolution R3).

    The picks decide whether a batch is held, so they have to resolve claims the
    way `next` does or the menu offers a batch someone is actively working. R3
    only consults a branch for a holder that already looks expired, so this
    costs a call for the rare abandoned-looking claim and nothing otherwise.

    The budget check is explicit because `last_commit_at` swallows `OSError`,
    and `TimeoutError` is one: without this a budget exhaustion would quietly
    become "no branch activity" -- the stale answer -- instead of sending the
    seed offline like every other exhausted call here.
    """
    def look(ref: str):
        if budget.remaining() <= 0:
            raise TimeoutError("seed budget exhausted")
        return last_commit_at(
            lambda args: run_gh(args, runner=budget.run), repo_slug(), ref)
    return look


def collect_live(
    *, budget: _Budget, now: datetime
) -> tuple[list[dict[str, Any]] | None, dict[int, dict[str, Any]], bool]:
    """Issues plus in-force claims. (None, {}, False) when GitHub is unreachable."""
    try:
        issues = fetch_issues(runner=budget.run)
    except Exception:
        return None, {}, False
    held: dict[int, dict[str, Any]] = {}
    for issue in issues:
        if CLAIM_LABEL not in label_names(issue):
            continue
        try:
            claim = resolve_claim(
                fetch_comments(int(issue["number"]), runner=budget.run), now=now,
                branch_activity_for=_branch_activity(budget),
            )
        except Exception:
            return issues, held, False
        if claim and not claim["stale"]:
            held[int(issue["number"])] = claim
    return issues, held, True


def fetch_prs(*, budget: _Budget) -> list[dict[str, Any]] | None:
    """Open PRs with their checks; None (no PR picks) when GitHub cannot answer."""
    try:
        proc = run_gh(["pr", "list", "--repo", repo_slug(), "--state", "open", "--limit", "50",
                       "--json", PR_FIELDS], runner=budget.run)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "[]")
    except ValueError:
        return None


def picks_now(*, offline: bool = False, limit: int = PICKS_SHOWN, thread: str | None = None,
              timeout: float = SEED_TIMEOUT_SEC) -> dict[str, Any]:
    """The ranked picks from the live state, plus when and from what they were read."""
    now = datetime.now(timezone.utc)
    roadmap = ROADMAP_STATUS.read_text(encoding="utf-8") if ROADMAP_STATUS.is_file() else None
    packages = load_packages()
    issues, held, prs, known = None, {}, None, False
    if not offline:
        budget = _Budget(timeout)
        issues, held, known = collect_live(budget=budget, now=now)
        prs = fetch_prs(budget=budget)
    live = with_inbox(packages, issues) if issues is not None else packages
    candidates = all_picks(roadmap_text=roadmap, packages=live, issues=issues, held=held, prs=prs)
    if thread:
        candidates.append(thread_pick(thread))
    source = "live" if issues is not None and prs is not None else (
        "partial" if issues is not None or prs is not None else "unavailable")
    if issues is not None and not known:
        source += " (claims unverified -- run `py -3 tools/backlog_triage.py next` before claiming)"
    return {"as_of": now.strftime("%Y-%m-%d %H:%MZ"), "source": source,
            "picks": rank(candidates, limit=limit)}


def session_brief_lines() -> list[str]:
    seed = picks_now(limit=SEED_LIMIT)
    return render_seed(seed["picks"], as_of=seed["as_of"], source=seed["source"])


# --------------------------------------------------------------------------
# lint (the text menu; the card is rendered by `card` and never hand-written)
# --------------------------------------------------------------------------

OPTION_RE = re.compile(r"^\s*(\d+)\.\s+(★\s+)?(.*)$")
RETIRED_LANE_RE = re.compile(r"`\[(thread|ship|backlog|decide|fix|park)\]`")
FILLER_RE = re.compile(r"^\W*(none|unavailable|n/a)\b", re.IGNORECASE)
PICK_RE = re.compile(r"^\*\*[^*]+\*\*\s+--\s+\S")


def _words(text: str) -> int:
    return len(text.split())


def lint(text: str) -> list[str]:
    """Problems with a rendered text menu; empty list means it passes."""
    problems: list[str] = []
    low = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase.lower() in low:
            problems.append(f"forbidden phrase: {phrase}")
    start = min(
        (i for i in (text.find(BETTER_ASK_LABEL), text.find(MENU_HEADING),
                     text.find(YOUR_CALL_HEADING)) if i >= 0),
        default=-1,
    )
    if start < 0:
        return problems + [f"missing {MENU_HEADING} (or {YOUR_CALL_HEADING}) heading"]
    footer = text[start:]
    if _words(footer) > FOOTER_MAX_WORDS:
        problems.append(f"footer is {_words(footer)} words (max {FOOTER_MAX_WORDS})")
    for line in footer.splitlines():
        if line.startswith(BETTER_ASK_LABEL) and _words(line) > BETTER_ASK_MAX_WORDS:
            problems.append(f"Better ask is {_words(line)} words (max {BETTER_ASK_MAX_WORDS})")
    options = [m for m in map(OPTION_RE.match, footer.splitlines()) if m]
    if YOUR_CALL_HEADING in footer and MENU_HEADING not in footer:
        if not 2 <= len(options) <= MAX_ANSWER_CHOICES:
            problems.append(f"{len(options)} answer choices (2-{MAX_ANSWER_CHOICES} expected)")
        return problems
    if not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
        problems.append(f"{len(options)} picks (expected {MIN_OPTIONS}-{MAX_OPTIONS})")
    numbers = [int(m.group(1)) for m in options]
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append(f"picks numbered {numbers}; expected 1..{len(numbers)}")
    stars = [m for m in options if m.group(2)]
    if len(stars) != 1 or (options and not options[0].group(2)):
        problems.append("exactly one star, on pick 1 (picks are ranked best first)")
    for m in options:
        body = m.group(3)
        if RETIRED_LANE_RE.search(body):
            problems.append(f"pick {m.group(1)} carries a retired lane tag; render `menu` instead")
        if FILLER_RE.match(body):
            problems.append(f"pick {m.group(1)} is filler; drop it rather than say none")
        elif not PICK_RE.match(body):
            problems.append(f"pick {m.group(1)} needs `**Title** -- reason`")
        if _words(body) > OPTION_MAX_WORDS:
            problems.append(f"pick {m.group(1)} is {_words(body)} words (max {OPTION_MAX_WORDS})")
    return problems


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, text in (("seed", "print the ranked picks with scores"),
                       ("menu", "print the text menu (Cursor, Codex, CLI)"),
                       ("card", "print the card HTML for the desktop app's show_widget tool")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--offline", action="store_true", help="skip GitHub; roadmap picks only")
        if name == "seed":
            p.add_argument("--json", action="store_true", help="include each pick's prompt")
        else:
            p.add_argument("--thread", metavar="'TITLE|REASON|PROMPT'",
                           help="your own next step in this conversation, ranked with the rest")
            p.add_argument("--say", action="append", default=[], metavar="'ID=HEADLINE|WHY'",
                           help="your plain-English wording for the pick with this id (repeat)")
    lt = sub.add_parser("lint", help="check a text menu (file path or - for stdin)")
    lt.add_argument("path")
    args = parser.parse_args(argv)

    if args.cmd == "lint":
        text = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
        problems = lint(text)
        print("footer OK" if not problems else "\n".join(f"- {p}" for p in problems))
        return 0 if not problems else 1
    try:
        seed = picks_now(offline=args.offline, thread=getattr(args, "thread", None),
                         limit=SEED_LIMIT if args.cmd == "seed" else PICKS_SHOWN)
    except ValueError as exc:
        parser.error(str(exc))
    if args.cmd == "seed":
        print(json.dumps(seed, indent=2) if args.json else
              "\n".join(render_seed(seed["picks"], as_of=seed["as_of"], source=seed["source"])))
    else:
        try:
            missing = apply_say(seed["picks"], args.say)
        except ValueError as exc:
            parser.error(str(exc))
        if missing:
            print(f"note: no shown pick has id {', '.join(missing)} (the ranking moved); "
                  "its default wording stays", file=sys.stderr)
        out = render_card(seed["picks"]) if args.cmd == "card" else render_menu(seed["picks"])
        print(out or "nothing worth offering -- skip the menu")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    raise SystemExit(main())
