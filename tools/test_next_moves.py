"""Tests for tools/next_moves.py -- the Next-move footer seed and lint."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import next_moves as nm  # noqa: E402

AGENTS = REPO_ROOT / "AGENTS.md"
RULE = REPO_ROOT / ".cursor" / "rules" / "next-move-footer.mdc"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy.yml"


def issue(number, *, labels=(), milestone=None, title=None):
    return {
        "number": number,
        "title": title or f"issue {number}",
        "labels": [{"name": n} for n in labels],
        "milestone": {"title": milestone, "number": 1} if milestone else None,
    }


PACKAGES = [
    {"rank": 1, "slug": "recorder", "title": "01 - Recorder", "readiness": "ready-now",
     "gate": "", "issues": [314, 318], "done": [],
     "prs": [{"title": "fix(recorder): no deadlock", "issues": [314, 318], "note": "", "gated": False}]},
    {"rank": 2, "slug": "state-truth", "title": "02 - State truth", "readiness": "ready-now",
     "gate": "", "issues": [316, 317], "done": [],
     "prs": [{"title": "fix(sim): server-owned recording state", "issues": [316, 317], "note": "", "gated": False}]},
    {"rank": 9, "slug": "replay-arch", "title": "09 - Replay", "readiness": "needs-decision-first",
     "gate": "THE CHOKEPOINT. #340 Phase 3: keep history_* as the single replay surface?",
     "issues": [340, 315, 308], "done": [],
     "prs": [{"title": "decide", "issues": [340], "note": "", "gated": True},
             {"title": "recorder source", "issues": [315, 308], "note": "", "gated": True}]},
    {"rank": 10, "slug": "desk", "title": "10 - Desk", "readiness": "ready-now",
     "gate": "#331 needs the operator at the PC", "issues": [331], "done": [],
     "prs": [{"title": "sunday", "issues": [331], "note": "", "gated": True}]},
]
ISSUES = [
    issue(314, labels=("P0", "bug", "claimed"), title="Recorder deadlock"),
    issue(318, labels=("P1", "bug", "claimed")),
    issue(316, labels=("P1", "bug")), issue(317, labels=("P1", "bug")),
    issue(340, labels=("P2", "decision")), issue(315, labels=("P0", "bug")),
    issue(308, labels=("P1", "bug")), issue(331, labels=("P1", "decision")),
]
HELD = {314: {"agent": "claude-wave-p01-0", "stale": False},
        318: {"agent": "claude-wave-p01-0", "stale": False}}

ROADMAP = """# Nova Roadmap Status

## Current position

- **Product NEXT:** **Phase K -- short entry**, `[~]` IN PROGRESS.
- **`auto_live`:** **NO-GO**

## Exact next action (human)

1. **K3 paper short days:** set `IBKR_SHORT_ENABLED=true` on paper Gateway; fill K3 Evidence.
2. **Reliability WS1:** leave the PC on overnight.

## Open phases
"""


# --------------------------------------------------------------------------
# roadmap ledger (the class of bug the dead `Active ops` regex hid)
# --------------------------------------------------------------------------


def test_product_next_parses_the_live_ledger():
    text = nm.ROADMAP_STATUS.read_text(encoding="utf-8")
    assert nm.product_next(text), "the real Nova-Roadmap-Status.md has no Product NEXT line"
    assert nm.human_next_items(text), "the real ledger has no 'Exact next action (human)' items"


def test_product_next_strips_bold_and_stops_at_next_heading():
    assert nm.product_next(ROADMAP) == "Phase K -- short entry, `[~]` IN PROGRESS."
    items = nm.human_next_items(ROADMAP)
    assert len(items) == 2 and items[0].startswith("K3 paper short days:")


def test_ship_lane_is_human_item_one_or_says_unavailable():
    assert nm.ship_lane(ROADMAP).startswith("K3 paper short days")
    assert nm.ship_lane(None).startswith("unavailable")


def test_live_ledger_ship_lane_is_not_withheld():
    """'before any live short' is a guardrail phrase, not an offer; it must render."""
    lane = nm.ship_lane(nm.ROADMAP_STATUS.read_text(encoding="utf-8"))
    assert lane != nm.WITHHELD and not lane.startswith("unavailable")


# --------------------------------------------------------------------------
# backlog / decide / p0 lanes
# --------------------------------------------------------------------------


def test_backlog_lane_offers_the_unclaimed_batch_and_names_the_holder_of_the_skipped_one():
    line = nm.backlog_lane(PACKAGES, ISSUES, HELD)
    assert line.startswith('Claim `state-truth` batch 0 and open its PR: "fix(sim): server-owned recording state" (#316, #317).')
    assert "`recorder` claimed by claude-wave-p01-0" in line


def test_backlog_lane_flags_unverified_claims():
    assert "Claims unverified" in nm.backlog_lane(PACKAGES, ISSUES, {}, claims_known=False)


def test_backlog_lane_never_offers_a_gated_batch():
    only_gated = [p for p in PACKAGES if p["slug"] in ("replay-arch", "desk")]
    assert nm.backlog_lane(only_gated, ISSUES, {}).startswith("none startable")


def test_decide_lane_picks_the_gate_that_frees_the_most_issues_and_marks_the_p0():
    line = nm.decide_lane(PACKAGES, ISSUES)
    assert line.startswith("Answer #340 (")
    assert "unblocks 3 issues, incl. P0 #315" in line


def test_decide_lane_says_none_pending_without_gates():
    assert nm.decide_lane(PACKAGES[:2], ISSUES) == "none pending"


def test_p0_line_reports_claim_state():
    line = nm.p0_line(ISSUES, HELD)
    assert "#314 Recorder deadlock (claimed by claude-wave-p01-0)" in line
    assert "#315" in line and "(unclaimed)" in line


def test_forbidden_phrases_are_withheld_from_every_lane():
    poisoned = [dict(PACKAGES[2], gate="#340 flip auto_live on for the replay?")]
    assert nm.decide_lane(poisoned, ISSUES) == nm.WITHHELD
    ledger = ROADMAP.replace("K3 paper short days:", "Go live now:")
    assert nm.ship_lane(ledger) == nm.WITHHELD


# --------------------------------------------------------------------------
# seed
# --------------------------------------------------------------------------


def test_build_seed_live_and_unavailable_shapes():
    live = nm.build_seed(roadmap_text=ROADMAP, packages=PACKAGES, issues=ISSUES, held=HELD, as_of="t")
    assert live["source"] == "live" and live["backlog"].startswith("Claim `state-truth`")
    down = nm.build_seed(roadmap_text=ROADMAP, packages=PACKAGES, issues=None, held=None, as_of="t")
    assert down["source"] == "unavailable"
    assert down["backlog"] == nm.UNAVAILABLE and down["ship"].startswith("K3")
    lines = nm.render_seed(live)
    assert lines[0].startswith("Next-move seed (as of t, source=live")
    assert [l.split("=")[0] for l in lines[1:]] == ["- product_next", "- ship", "- backlog", "- decide", "- p0"]


def test_seed_offline_cli_never_touches_github(capsys, monkeypatch):
    def _boom(**kw):
        raise AssertionError("gh must not be called offline")

    monkeypatch.setattr(nm, "fetch_issues", _boom)
    assert nm.main(["seed", "--offline"]) == 0
    out = capsys.readouterr().out
    assert "source=unavailable" in out and "- ship=" in out


def test_collect_live_fails_open_when_gh_is_unreachable(monkeypatch):
    def _down(**kw):
        raise RuntimeError("gh issue list failed")

    monkeypatch.setattr(nm, "fetch_issues", _down)
    from datetime import datetime, timezone

    issues, held, known = nm.collect_live(budget=nm._Budget(1), now=datetime.now(timezone.utc))
    assert issues is None and held == {} and known is False


# --------------------------------------------------------------------------
# lint
# --------------------------------------------------------------------------


def _rule_example() -> str:
    text = RULE.read_text(encoding="utf-8")
    block = text.split("## Example", 1)[1]
    return block.split("```text", 1)[1].split("```", 1)[0]


def test_rule_example_passes_the_lint():
    assert nm.lint(_rule_example()) == []


def test_lint_rejects_bad_shapes():
    good = _rule_example()
    assert any("forbidden" in p for p in nm.lint(good + "\nalso enable auto_live"))
    assert any("starred" in p for p in nm.lint(good.replace("★ ", "", 1)))
    two_stars = good.replace("2. `[ship]`", "2. ★ `[ship]`")
    assert any("starred" in p for p in nm.lint(two_stars))
    starred_decide = good.replace("1. ★ `[thread]`", "1. `[thread]`").replace("4. `[decide]`", "4. ★ `[decide]`")
    assert any("[decide]" in p for p in nm.lint(starred_decide))
    reordered = good.replace("2. `[ship]`", "2. `[backlog]`").replace("3. `[backlog]`", "3. `[ship]`")
    assert any("out of order" in p for p in nm.lint(reordered))
    long_option = good.replace("(0/3 days).", "(0/3 days) " + "word " * 25)
    assert any("words (max" in p for p in nm.lint(long_option))
    assert any("missing" in p for p in nm.lint("just a reply with no menu"))


def test_lint_accepts_question_mode_and_failure_mode():
    question = "**Your call** (reply with a number; `0` = other):\n1. ★ `[thread]` Keep four lanes. -- cheapest\n2. `[thread]` Cut to three lanes.\n"
    assert nm.lint(question) == []
    failure = (
        "**Next move** (reply with a number):\n"
        "1. ★ `[fix]` Make the lock re-entrant in backend/capture/recorder.py; done when the stop test passes. -- root cause\n"
        "2. `[park]` Open a `deferred` issue (P1, domain:capture) with Symptom / Cause-so-far.\n"
        "3. `[backlog]` Claim `state-truth` batch 0 and open its PR (#316, #317).\n"
    )
    assert nm.lint(failure) == []


# --------------------------------------------------------------------------
# single home: the constitution names the lanes in order but carries no option line
# --------------------------------------------------------------------------


def _footer_bullet() -> str:
    text = AGENTS.read_text(encoding="utf-8")
    start = text.index("**Next-move footer**")
    return text[start:start + 1500]


def test_agents_md_names_the_lanes_in_order_and_points_at_the_rule_and_seed():
    bullet = _footer_bullet()
    positions = [bullet.index(f"`[{lane}]`") for lane in nm.LANES]
    assert positions == sorted(positions)
    assert "next-move-footer.mdc" in bullet and "tools/next_moves.py" in bullet


def test_agents_md_carries_no_option_line():
    option = re.compile(r"^\s*\d+\.\s+(★\s+)?`\[(thread|ship|backlog|decide)\]`", re.MULTILINE)
    assert not option.search(AGENTS.read_text(encoding="utf-8"))


def test_rule_names_the_lanes_in_order_and_is_always_on():
    text = RULE.read_text(encoding="utf-8")
    assert "alwaysApply: true" in text
    positions = [text.index(f"`[{lane}]`") for lane in nm.LANES]
    assert positions == sorted(positions)


def test_ci_runs_this_file():
    assert "tools/test_next_moves.py" in DEPLOY.read_text(encoding="utf-8")
