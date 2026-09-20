#!/usr/bin/env python3
"""Next-move footer: grounded seed + lint (AGENTS.md §5, next-move-footer.mdc).

Read-only. `seed` prints the lines an agent copies into the **Next move**
menu -- [ship] from the roadmap ledger, [backlog] from the same selection
`backlog_triage.py next` uses, [decide] from the gated batches in
knowledge/backlog-packages.json, p0 from the open issues -- so no issue
number, package slug or PR title is ever recalled from memory. `lint`
checks a rendered footer against the shape and the forbidden phrases.

Every GitHub call is bounded by SEED_TIMEOUT_SEC; when the network is
unavailable the seed still renders, with the missing lane saying so. The
session brief calls `session_brief_lines()` once per session.
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

from tools.backlog_claims import CLAIM_LABEL, active_claim  # noqa: E402
from tools.backlog_github import (  # noqa: E402
    fetch_comments,
    fetch_issues,
    label_names,
    severity_of,
)
from tools.backlog_plan import load_packages, next_pr, pick_next, with_inbox  # noqa: E402

ROADMAP_STATUS = (
    REPO_ROOT / "knowledge" / "obsidian" / "03-Nova-Decisions" / "Nova-Roadmap-Status.md"
)

# ---- footer contract (single home; AGENTS.md §5 and the .mdc cite these) ----
LANES: tuple[str, ...] = ("thread", "ship", "backlog", "decide")
FAILURE_LANES: tuple[str, ...] = ("fix", "park")
MENU_HEADING = "**Next move**"
YOUR_CALL_HEADING = "**Your call**"
BETTER_ASK_LABEL = "**Better ask:**"
STAR = "★"
MIN_OPTIONS = 3
MAX_OPTIONS = 5
OPTION_MAX_WORDS = 30
BETTER_ASK_MAX_WORDS = 35
FOOTER_MAX_WORDS = 180
# Offers that may never appear in a lane. "live short" is deliberately absent:
# the roadmap ledger uses it as a guardrail phrase ("before any live short").
FORBIDDEN_PHRASES: tuple[str, ...] = (
    "auto_live",
    "IBKR_LIVE_TRADING_CONFIRMED=true",
    "go live",
)
WITHHELD = "[withheld: NO-GO]"

# ---- seed sources ----
PRODUCT_NEXT_RE = re.compile(r"^-\s*\*\*Product NEXT:\*\*\s*(.+)$", re.MULTILINE)
HUMAN_NEXT_HEADING = "## Exact next action (human)"
NUMBERED_RE = re.compile(r"^\s*\d+\.\s+(.+)$")
ISSUE_RE = re.compile(r"#(\d+)")
SEED_TIMEOUT_SEC = 8
TITLE_MAX_CHARS = 90
SHIP_MAX_CHARS = 170
QUESTION_MAX_CHARS = 110
LEGACY_PREFIX_RE = re.compile(r"^(?:D-\d+\s*--\s*)?(?:P[0-3]:\s*)?")
UNAVAILABLE = "unavailable -- run `py -3 tools/backlog_triage.py next`"


# --------------------------------------------------------------------------
# roadmap ledger
# --------------------------------------------------------------------------


def _plain(text: str) -> str:
    return re.sub(r"\*\*", "", text).strip()


def product_next(text: str) -> str | None:
    m = PRODUCT_NEXT_RE.search(text)
    return _plain(m.group(1)) if m else None


def human_next_items(text: str) -> list[str]:
    """Numbered items under 'Exact next action (human)', markdown bold removed."""
    if HUMAN_NEXT_HEADING not in text:
        return []
    body = text.split(HUMAN_NEXT_HEADING, 1)[1]
    body = re.split(r"^## ", body, maxsplit=1, flags=re.MULTILINE)[0]
    return [_plain(m.group(1)) for m in map(NUMBERED_RE.match, body.splitlines()) if m]


def ship_lane(roadmap_text: str | None) -> str:
    items = human_next_items(roadmap_text or "")
    if not items:
        return "unavailable -- read Nova-Roadmap-Status.md 'Exact next action (human)'"
    return _guard(_clip(items[0], SHIP_MAX_CHARS))


# --------------------------------------------------------------------------
# backlog / decide / p0
# --------------------------------------------------------------------------


def _clip(text: str, limit: int = TITLE_MAX_CHARS) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _guard(text: str) -> str:
    low = text.lower()
    return WITHHELD if any(p.lower() in low for p in FORBIDDEN_PHRASES) else text


def backlog_lane(
    packages: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    held: dict[int, dict[str, Any]],
    *,
    claims_known: bool = True,
) -> str:
    open_numbers = {int(i["number"]) for i in issues}
    pkg, skipped = pick_next(packages, open_numbers, held)
    if pkg is None:
        return "none startable -- everything left is gated or claimed"
    pr = next_pr(pkg, open_numbers, held)
    if pr is None:
        return "none startable -- everything left is gated or claimed"
    index = pkg["prs"].index(pr)
    numbers = ", ".join(f"#{n}" for n in pr["issues"] if n in open_numbers)
    line = f'Claim `{pkg["slug"]}` batch {index} and open its PR: "{_clip(pr["title"])}" ({numbers}).'
    tails = []
    for s in skipped:
        if "claimed" in (s.get("_skip_reason") or ""):
            holder = next(
                (held[n].get("agent", "?") for n in s["issues"] if n in held), "another agent"
            )
            tails.append(f"`{s['slug']}` claimed by {holder}")
    if tails:
        line += " Skipped: " + "; ".join(tails) + "."
    if not claims_known:
        line += " Claims unverified -- run `py -3 tools/backlog_triage.py next` before claiming."
    return _guard(line)


def decide_lane(packages: list[dict[str, Any]], issues: list[dict[str, Any]]) -> str:
    """The gated package that frees the most open issues, phrased as a question."""
    open_numbers = {int(i["number"]) for i in issues}
    p0 = {int(i["number"]) for i in issues if severity_of(i) == "P0"}
    best: tuple[int, int, dict[str, Any], list[int]] | None = None
    for pkg in packages:
        gated = [
            n for pr in pkg.get("prs", []) if pr.get("gated")
            for n in pr["issues"] if n in open_numbers
        ]
        if not gated:
            continue
        key = (-len(gated), int(pkg.get("rank", 99)))
        if best is None or key < (best[0], best[1]):
            best = (key[0], key[1], pkg, gated)
    if best is None:
        return "none pending"
    pkg, gated = best[2], best[3]
    gate = pkg.get("gate") or ""
    m = ISSUE_RE.search(gate)
    number = int(m.group(1)) if m else gated[0]
    question = gate.split(":", 1)[1] if ":" in gate else gate
    question = _clip(re.split(r"(?<=[.?!])\s+", question.strip(), maxsplit=1)[0], QUESTION_MAX_CHARS)
    question = question.rstrip(".") or "see the issue"
    incl = f", incl. P0 #{min(p0 & set(gated))}" if p0 & set(gated) else ""
    return _guard(f"Answer #{number} ({question}) -- unblocks {len(gated)} issues{incl}.")


def p0_line(issues: list[dict[str, Any]], held: dict[int, dict[str, Any]]) -> str:
    hot = sorted((int(i["number"]), i) for i in issues if severity_of(i) == "P0")
    if not hot:
        return "none open"
    parts = []
    for number, issue in hot[:3]:
        state = f"claimed by {held[number].get('agent', '?')}" if number in held else "unclaimed"
        title = LEGACY_PREFIX_RE.sub("", issue.get("title", ""), count=1)
        parts.append(f"#{number} {_clip(title, 60)} ({state})")
    return "; ".join(parts)


# --------------------------------------------------------------------------
# seed
# --------------------------------------------------------------------------


def build_seed(
    *,
    roadmap_text: str | None,
    packages: list[dict[str, Any]],
    issues: list[dict[str, Any]] | None,
    held: dict[int, dict[str, Any]] | None,
    as_of: str,
    claims_known: bool = True,
) -> dict[str, Any]:
    seed: dict[str, Any] = {
        "as_of": as_of,
        "source": "live" if issues is not None else "unavailable",
        "product_next": product_next(roadmap_text or "") or "unavailable",
        "ship": ship_lane(roadmap_text),
    }
    if issues is None:
        seed.update(backlog=UNAVAILABLE, decide=UNAVAILABLE, p0=UNAVAILABLE)
        return seed
    live = with_inbox(packages, issues)
    holders = held or {}
    seed["backlog"] = backlog_lane(live, issues, holders, claims_known=claims_known)
    seed["decide"] = decide_lane(live, issues)
    seed["p0"] = p0_line(issues, holders)
    return seed


def render_seed(seed: dict[str, Any], *, with_product_next: bool = True) -> list[str]:
    lines = [
        f"Next-move seed (as of {seed['as_of']}, source={seed['source']}; "
        "copy these into the footer lanes, never from memory):",
    ]
    if with_product_next:
        lines.append(f"- product_next= {seed['product_next']}")
    return lines + [
        f"- ship= {seed['ship']}",
        f"- backlog= {seed['backlog']}",
        f"- decide= {seed['decide']}",
        f"- p0= {seed['p0']}",
    ]


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
            claim = active_claim(fetch_comments(int(issue["number"]), runner=budget.run), now=now)
        except Exception:
            return issues, held, False
        if claim and not claim["stale"]:
            held[int(issue["number"])] = claim
    return issues, held, True


def seed_now(*, offline: bool = False, timeout: float = SEED_TIMEOUT_SEC) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    roadmap = ROADMAP_STATUS.read_text(encoding="utf-8") if ROADMAP_STATUS.is_file() else None
    packages = load_packages()
    if offline:
        issues, held, known = None, {}, False
    else:
        issues, held, known = collect_live(budget=_Budget(timeout), now=now)
    return build_seed(
        roadmap_text=roadmap, packages=packages, issues=issues, held=held,
        as_of=now.strftime("%Y-%m-%d %H:%MZ"), claims_known=known,
    )


def session_brief_lines() -> list[str]:
    """The brief already prints `Roadmap NEXT:`, so the seed omits product_next there."""
    return render_seed(seed_now(), with_product_next=False)


# --------------------------------------------------------------------------
# lint
# --------------------------------------------------------------------------

OPTION_RE = re.compile(r"^\s*(\d+)\.\s+(★\s+)?(.*)$")
TAG_RE = re.compile(r"`\[(\w+)\]`")


def _words(text: str) -> int:
    return len(text.split())


def lint(text: str) -> list[str]:
    """Problems with a rendered footer; empty list means it passes."""
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
        if not MIN_OPTIONS - 1 <= len(options) <= MAX_OPTIONS:
            problems.append(f"{len(options)} answer choices (2-{MAX_OPTIONS} expected)")
        return problems
    if not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
        problems.append(f"{len(options)} options (expected {MIN_OPTIONS}-{MAX_OPTIONS})")
    numbers = [int(m.group(1)) for m in options]
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append(f"options numbered {numbers}; expected 1..{len(numbers)}")
    stars = [m for m in options if m.group(2)]
    if len(stars) != 1:
        problems.append(f"{len(stars)} starred options (exactly one expected)")
    tags: list[str] = []
    for m in options:
        body = m.group(3)
        tag = TAG_RE.search(body)
        if not tag:
            problems.append(f"option {m.group(1)} has no `[lane]` tag")
            continue
        tags.append(tag.group(1))
        if tag.group(1) not in LANES + FAILURE_LANES:
            problems.append(f"option {m.group(1)} has unknown lane [{tag.group(1)}]")
        if m.group(2) and tag.group(1) == "decide":
            problems.append("the star may not sit on [decide] -- the operator decides")
        if _words(body) > OPTION_MAX_WORDS:
            problems.append(f"option {m.group(1)} is {_words(body)} words (max {OPTION_MAX_WORDS})")
    order = [t for t in tags if t in LANES]
    if order != sorted(order, key=LANES.index):
        problems.append(f"lanes out of order {order}; expected {list(LANES)} order")
    return problems


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed", help="print the grounded lane seed")
    s.add_argument("--json", action="store_true")
    s.add_argument("--offline", action="store_true", help="skip GitHub; roadmap lanes only")
    lt = sub.add_parser("lint", help="check a rendered footer (file path or - for stdin)")
    lt.add_argument("path")
    args = parser.parse_args(argv)

    if args.cmd == "seed":
        seed = seed_now(offline=args.offline)
        print(json.dumps(seed, indent=2) if args.json else "\n".join(render_seed(seed)))
        return 0
    text = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
    problems = lint(text)
    print("footer OK" if not problems else "\n".join(f"- {p}" for p in problems))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
