"""Ranked next-move picks: every real candidate, scored, so the menu offers the best three.

The old footer had four fixed lanes that had to be filled every time, so an empty
lane got filler and a P1 bug in the inbox never appeared (operator report
2026-10-13). Here every source -- open PRs, open P0/P1 bugs (untriaged ones
included), the backlog's next batch, the inbox, gated decisions and the roadmap's
human steps -- turns into zero or more candidates, each with a score from the one
table below and a one-line reason. `rank` keeps the best few. Pure: callers hand
in what they fetched, nothing here touches GitHub.
"""

from __future__ import annotations

import re
from typing import Any

from tools.backlog_footprints import claim_conflicts
from tools.backlog_github import INBOX_TITLE, label_names, milestone_title, severity_of
from tools.backlog_plan import next_pr, pick_next
from tools.release_gate import REQUIRED_CHECKS

# ---- the one scoring table (higher first; the menu shows the top PICKS_SHOWN) ----
SCORE_THREAD = 92          # the agent's own next step in this conversation
SCORE_PR_RED = 85          # nothing merges red; a red PR is work already paid for
SCORE_PR_CONFLICT = 75     # often a sibling session's PR that master just moved under
SEVERITY_SCORE = {"P0": 95, "P1": 80, "P2": 55, "P3": 40}
MONEY_PATH_BONUS = 5       # an execution bug touches orders and positions
PLAN_NEXT_BONUS = 5        # the batch the authored plan would hand out next
SCORE_BATCH_FLOOR = 50
SCORE_TRIAGE_URGENT = 70   # a P0/P1 in the inbox: `next` cannot hand it out
SCORE_TRIAGE_BASE = 45
SCORE_DECIDE_BASE = 50
SCORE_DECIDE_PER_ISSUE = 3
SCORE_DECIDE_MAX = 75
SCORE_OPERATOR_STEP = 40
SCORE_FLOOR = 40           # below this a candidate is filler and never shown
PICKS_SHOWN = 3
MAX_PER_KIND = 2           # three red PRs must not crowd out everything else
# Ties break by kind, in this order: open work before new work, work before asks.
KIND_ORDER = ("thread", "pr", "fix", "batch", "decide", "triage", "operator")

MONEY_PATH_DOMAINS = frozenset({"domain:execution"})
PR_TITLE_CHARS = 60
HOLD_LABELS = frozenset({"do-not-merge"})
CLAIM_LABEL_NAME = "claimed"

# Offers that may never appear. "live short" is deliberately absent: the roadmap
# ledger uses it as a guardrail phrase ("before any live short").
FORBIDDEN_PHRASES: tuple[str, ...] = (
    "auto_live",
    "IBKR_LIVE_TRADING_CONFIRMED=true",
    "go live",
)

TITLE_MAX_CHARS = 40
REASON_MAX_CHARS = 120
LEGACY_PREFIX_RE = re.compile(r"^(?:D-\d+\s*--\s*)?(?:P[0-3]:\s*)?")
ISSUE_RE = re.compile(r"#(\d+)")
HUMAN_NEXT_HEADING = "## Exact next action (human)"
NUMBERED_RE = re.compile(r"^\s*\d+\.\s+(.+)$")


def clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,;:-") + "…"


def forbidden(text: str) -> bool:
    low = text.lower()
    return any(p.lower() in low for p in FORBIDDEN_PHRASES)


def pick(kind: str, score: int, title: str, reason: str, badge: str, tone: str,
         prompt: str) -> dict[str, Any]:
    """One candidate. `tone` colours the badge: danger, warning, accent or neutral."""
    return {"kind": kind, "score": int(score), "title": clip(title, TITLE_MAX_CHARS),
            "reason": clip(reason, REASON_MAX_CHARS), "badge": badge, "tone": tone,
            "prompt": " ".join(prompt.split())}


def _issue_title(issue: dict[str, Any]) -> str:
    return LEGACY_PREFIX_RE.sub("", str(issue.get("title") or ""), count=1).strip()


# --------------------------------------------------------------------------
# open pull requests
# --------------------------------------------------------------------------


def red_checks(rollup: list[dict[str, Any]]) -> list[str]:
    """Required checks whose newest run finished anything but green ("skipped" is red too)."""
    red = []
    for check in REQUIRED_CHECKS:
        runs = [r for r in rollup or [] if str(r.get("name") or "") == check]
        if not runs:
            continue
        newest = max(runs, key=lambda r: str(r.get("startedAt") or ""))
        if str(newest.get("status") or "").upper() != "COMPLETED":
            continue
        if str(newest.get("conclusion") or "").upper() != "SUCCESS":
            red.append(check)
    return red


def pr_picks(prs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A red or conflicting ready PR. Drafts and `do-not-merge` are holds someone chose."""
    out = []
    for pr in prs:
        if pr.get("isDraft") or label_names(pr) & HOLD_LABELS:
            continue
        number, title = int(pr["number"]), str(pr.get("title") or "")
        red = red_checks(pr.get("statusCheckRollup") or [])
        if red:
            out.append(pick(
                "pr", SCORE_PR_RED, f"Get PR #{number} green",
                f"{', '.join(red)} failed on \"{clip(title, PR_TITLE_CHARS)}\"; nothing merges red.",
                "PR red", "danger",
                f"Get PR #{number} green: read the failed {', '.join(red)} log, fix the cause "
                "on its branch, push, and confirm the checks pass.",
            ))
        elif str(pr.get("mergeable") or "").upper() == "CONFLICTING":
            out.append(pick(
                "pr", SCORE_PR_CONFLICT, f"Unblock PR #{number}",
                f"\"{clip(title, PR_TITLE_CHARS)}\" conflicts with master, so Actions cannot merge it.",
                "PR conflict", "warning",
                f"Resolve PR #{number}'s merge conflict with master on its branch, re-run "
                "the checks, and confirm it is mergeable.",
            ))
    return out


# --------------------------------------------------------------------------
# backlog: urgent bugs, the plan's next batch, the inbox, decisions
# --------------------------------------------------------------------------


def _batch_of(packages: list[dict[str, Any]], number: int):
    for pkg in packages:
        if pkg.get("title") == INBOX_TITLE:
            continue
        for index, pr in enumerate(pkg.get("prs", [])):
            if number in pr.get("issues", []):
                return pkg, index, pr
    return None


def _batch_pick(pkg: dict[str, Any], index: int, pr: dict[str, Any], score: int,
                lead: dict[str, Any] | None, open_numbers: set[int]) -> dict[str, Any]:
    numbers = [n for n in pr["issues"] if n in open_numbers]
    refs = ", ".join(f"#{n}" for n in numbers)
    sev = severity_of(lead) if lead else ""
    reason = (f"{sev} #{lead['number']}: {_issue_title(lead)}" if lead and sev in ("P0", "P1")
              else f'{pkg["title"]}: "{pr["title"]}"')
    return pick(
        "batch", score, f"Claim {pkg['slug']} batch {index}", f"{reason} ({refs})",
        sev or "Backlog", "danger" if sev in ("P0", "P1") else "accent",
        f"Claim `{pkg['slug']}` batch {index} with backlog_triage.py claim, branch from "
        f'origin/master, and open its PR: "{pr["title"]}" ({refs}).',
    )


def backlog_picks(packages: list[dict[str, Any]], issues: list[dict[str, Any]],
                  held: dict[int, Any]) -> list[dict[str, Any]]:
    """Urgent bugs (as their batch, or alone when untriaged) plus the plan's next batch.

    A gated or claimed issue is never offered as work: a gate is the operator's
    (see `decide_pick`), a claim is another agent's.
    """
    by_number = {int(i["number"]): i for i in issues}
    open_numbers = set(by_number)
    out: dict[tuple, dict[str, Any]] = {}
    for number, issue in sorted(by_number.items()):
        sev = severity_of(issue)
        names = label_names(issue)
        if sev not in ("P0", "P1") or number in held or CLAIM_LABEL_NAME in names:
            continue
        if "decision" in names:
            continue
        score = SEVERITY_SCORE[sev] + (MONEY_PATH_BONUS if names & MONEY_PATH_DOMAINS else 0)
        found = _batch_of(packages, number)
        if milestone_title(issue) == INBOX_TITLE or found is None:
            out[("fix", number)] = pick(
                "fix", score, f"Fix #{number}", _issue_title(issue),
                f"{sev} · money path" if names & MONEY_PATH_DOMAINS else sev, "danger",
                f"Fix #{number} ({_issue_title(issue)}): route it into its package, claim it, "
                "branch from origin/master, fix the root cause with a regression test, open the PR.",
            )
            continue
        pkg, index, pr = found
        if pr.get("gated") or set(pr["issues"]) & set(held):
            continue
        if claim_conflicts(pkg, pr, held, packages):
            continue
        key = ("batch", pkg["slug"], index)
        if key not in out or out[key]["score"] < score:
            out[key] = _batch_pick(pkg, index, pr, score, issue, open_numbers)
    pkg, _skipped = pick_next(packages, open_numbers, held)
    if pkg is not None:
        pr = next_pr(pkg, open_numbers, held, packages=packages)
        if pr is not None:
            index = pkg["prs"].index(pr)
            key = ("batch", pkg["slug"], index)
            worst = min((SEVERITY_SCORE.get(severity_of(by_number[n]), SCORE_BATCH_FLOOR)
                         for n in pr["issues"] if n in by_number), default=SCORE_BATCH_FLOOR)
            score = max(worst, SCORE_BATCH_FLOOR) + PLAN_NEXT_BONUS
            if key in out:
                out[key]["score"] += PLAN_NEXT_BONUS
            else:
                out[key] = _batch_pick(pkg, index, pr, score, None, open_numbers)
    return list(out.values())


def triage_pick(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queued = [i for i in issues if milestone_title(i) == INBOX_TITLE]
    if not queued:
        return []
    urgent = sorted(int(i["number"]) for i in queued if severity_of(i) in ("P0", "P1"))
    score = SCORE_TRIAGE_URGENT if urgent else SCORE_TRIAGE_BASE + min(len(queued), 10)
    incl = f", incl. {', '.join(f'#{n}' for n in urgent[:3])}" if urgent else ""
    return [pick(
        "triage", score, "Triage the inbox",
        f"{len(queued)} issues wait in {INBOX_TITLE}{incl}; `next` cannot hand them out.",
        "Unblocks the backlog", "warning",
        f"Triage the backlog: route every issue in {INBOX_TITLE} into the package whose "
        "outcome it serves, run sync, and open one PR with the JSON change.",
    )]


def decide_pick(packages: list[dict[str, Any]], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The gated package that frees the most open issues -- a step only the operator can take."""
    open_numbers = {int(i["number"]) for i in issues}
    p0 = {int(i["number"]) for i in issues if severity_of(i) == "P0"}
    best = None
    for pkg in packages:
        if pkg.get("title") == INBOX_TITLE:
            continue
        gated = sorted({n for pr in pkg.get("prs", []) if pr.get("gated")
                        for n in pr["issues"] if n in open_numbers})
        if gated and (best is None or (-len(gated), pkg.get("rank", 99)) < best[0]):
            best = ((-len(gated), pkg.get("rank", 99)), pkg, gated)
    if best is None:
        return []
    _key, pkg, gated = best
    gate = str(pkg.get("gate") or "")
    if forbidden(gate):
        return []
    m = ISSUE_RE.search(gate)
    number = int(m.group(1)) if m else gated[0]
    first = re.split(r"(?<=[.?!])\s+", gate.strip(), maxsplit=1)[0] or "see the issue"
    score = min(SCORE_DECIDE_BASE + SCORE_DECIDE_PER_ISSUE * len(gated), SCORE_DECIDE_MAX)
    if p0 & set(gated):
        score = SEVERITY_SCORE["P0"]  # a P0 waits on this answer
    return [pick(
        "decide", score, f"Unblock #{number}", first,
        f"Only you · frees {len(gated)}", "neutral",
        f"Show me what #{number} needs from me -- the question or the evidence -- in plain "
        "words with the options and your recommendation, then wait for my answer.",
    )]


# --------------------------------------------------------------------------
# roadmap: the steps only the operator can take
# --------------------------------------------------------------------------


def human_next_items(text: str) -> list[str]:
    """Numbered items under 'Exact next action (human)', markdown bold removed."""
    if HUMAN_NEXT_HEADING not in text:
        return []
    body = text.split(HUMAN_NEXT_HEADING, 1)[1]
    body = re.split(r"^## ", body, maxsplit=1, flags=re.MULTILINE)[0]
    return [re.sub(r"\*\*", "", m.group(1)).strip()
            for m in map(NUMBERED_RE.match, body.splitlines()) if m]


def operator_picks(roadmap_text: str | None) -> list[dict[str, Any]]:
    """The first roadmap human step that is an action (a ban is a guardrail, not a step)."""
    for item in human_next_items(roadmap_text or ""):
        if forbidden(item) or ":" not in item:
            continue
        label, rest = (s.strip() for s in item.split(":", 1))
        first = re.split(r"(?<=[.?!])\s+", rest, maxsplit=1)[0]
        return [pick(
            "operator", SCORE_OPERATOR_STEP, label, first, "Only you · roadmap", "neutral",
            f"Walk me through the roadmap step '{label}': what it asks of me, what is "
            "already done, and the smallest next action I can take today.",
        )]
    return []


# --------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------


def thread_pick(spec: str) -> dict[str, Any]:
    """`Title|reason|prompt` from the agent: its own next step in this conversation."""
    parts = [p.strip() for p in spec.split("|")]
    if len(parts) != 3 or not all(parts):
        raise ValueError("--thread takes 'Title|one-line reason|prompt'")
    return pick("thread", SCORE_THREAD, parts[0], parts[1], "This thread", "accent", parts[2])


def rank(candidates: list[dict[str, Any]], limit: int = PICKS_SHOWN) -> list[dict[str, Any]]:
    """Best first, filler dropped, at most MAX_PER_KIND of a kind, forbidden offers withheld."""
    kept: list[dict[str, Any]] = []
    per_kind: dict[str, int] = {}
    for c in sorted(candidates, key=lambda c: (-c["score"], KIND_ORDER.index(c["kind"]), c["title"])):
        if c["score"] < SCORE_FLOOR or forbidden(" ".join((c["title"], c["reason"], c["prompt"]))):
            continue
        if per_kind.get(c["kind"], 0) >= MAX_PER_KIND:
            continue
        per_kind[c["kind"]] = per_kind.get(c["kind"], 0) + 1
        kept.append(c)
        if len(kept) == limit:
            break
    return kept


def all_picks(*, roadmap_text: str | None, packages: list[dict[str, Any]],
              issues: list[dict[str, Any]] | None, held: dict[int, Any] | None,
              prs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Every candidate from what was fetched; a source that could not be read adds none."""
    out = operator_picks(roadmap_text)
    if prs is not None:
        out += pr_picks(prs)
    if issues is not None:
        out += backlog_picks(packages, issues, held or {})
        out += triage_pick(issues)
        out += decide_pick(packages, issues)
    return out
