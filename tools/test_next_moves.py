"""Tests for the Next-move picks: tools/next_moves.py, next_move_picks.py, next_move_render.py."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import next_move_picks as picks  # noqa: E402
from tools import next_move_render as render  # noqa: E402
from tools import next_moves as nm  # noqa: E402

AGENTS = REPO_ROOT / "AGENTS.md"
RULE = REPO_ROOT / ".cursor" / "rules" / "next-move-footer.mdc"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
INBOX = "00 - Untriaged"


def issue(number, *, labels=(), milestone=None, title=None):
    return {
        "number": number,
        "title": title or f"issue {number}",
        "labels": [{"name": n} for n in labels],
        "milestone": {"title": milestone, "number": 1} if milestone else None,
    }


def batch(title, issues, gated=False):
    return {"title": title, "issues": issues, "note": "", "gated": gated}


PACKAGES = [
    {"rank": 0, "slug": "untriaged", "title": INBOX, "readiness": "needs-triage",
     "gate": "Needs a routing decision", "issues": [], "done": [], "prs": []},
    {"rank": 1, "slug": "recorder", "title": "01 - Recorder", "readiness": "ready-now",
     "gate": "", "issues": [314, 318], "done": [],
     "prs": [batch("fix(recorder): no deadlock", [314, 318])]},
    {"rank": 2, "slug": "state-truth", "title": "02 - State truth", "readiness": "ready-now",
     "gate": "", "issues": [316, 317], "done": [],
     "prs": [batch("fix(sim): server-owned recording state", [316, 317])]},
    {"rank": 9, "slug": "replay-arch", "title": "09 - Replay", "readiness": "needs-decision-first",
     "gate": "#340 Phase 3: keep history_* as the single replay surface? More detail.",
     "issues": [340, 315, 308], "done": [],
     "prs": [batch("decide", [340], gated=True), batch("recorder source", [315, 308], gated=True)]},
    {"rank": 10, "slug": "desk", "title": "10 - Desk", "readiness": "ready-now",
     "gate": "#331 needs the operator at the PC", "issues": [331], "done": [],
     "prs": [batch("sunday", [331], gated=True)]},
]
ISSUES = [
    issue(314, labels=("P0", "bug", "claimed"), title="Recorder deadlock"),
    issue(318, labels=("P1", "bug", "claimed")),
    issue(316, labels=("P1", "bug"), title="Recording state lies"), issue(317, labels=("P2", "bug")),
    issue(340, labels=("P2", "decision")), issue(315, labels=("P0", "bug")),
    issue(308, labels=("P1", "bug")), issue(331, labels=("P1", "decision")),
    issue(913, labels=("P1", "bug", "domain:execution"), milestone=INBOX,
          title="Orders stay enabled on a Level 2 with no book"),
    issue(722, labels=("P1", "bug", "domain:ibkr"), milestone=INBOX, title="Silent T&S lines"),
    issue(927, labels=("P2", "bug"), milestone=INBOX),
]
HELD = {314: {"agent": "claude-wave-p01-0", "stale": False},
        318: {"agent": "claude-wave-p01-0", "stale": False}}

ROADMAP = """# Nova Roadmap Status

## Exact next action (human)

1. **Phase L research:** review strategy results and choose a question. Done when recorded.
2. **Reliability WS1:** leave the PC on overnight.
3. **Hard ban:** no `auto_live` or Live bot.

## Open phases
"""


def run(name, conclusion="SUCCESS", status="COMPLETED", at="2026-10-14T01:00:00Z"):
    return {"name": name, "status": status, "conclusion": conclusion, "startedAt": at}


def green_rollup():
    return [run(c) for c in picks.REQUIRED_CHECKS]


def live_picks(issues=ISSUES):
    live = nm.with_inbox(PACKAGES, issues)
    return picks.all_picks(roadmap_text=ROADMAP, packages=live, issues=issues, held=HELD, prs=[])


def calm_picks():
    """The same backlog with no P0 waiting on a decision."""
    return live_picks([i for i in ISSUES if i["number"] != 315])


# --------------------------------------------------------------------------
# the regression: the menu hid the P1s and offered filler (operator report 2026-10-13)
# --------------------------------------------------------------------------


def test_an_untriaged_p1_on_the_money_path_is_offered_and_ranks_by_value():
    ranked = picks.rank(live_picks())
    # A P0 waits on #340's answer, so that ask leads; the inbox P1 is next, never hidden.
    assert [p["title"] for p in ranked] == ["Unblock #340", "Fix #913", "Claim state-truth batch 0"]
    assert ranked[1]["badge"] == "P1 · money path"
    assert ranked[1]["score"] == picks.SEVERITY_SCORE["P1"] + picks.MONEY_PATH_BONUS
    assert picks.rank(calm_picks())[0]["title"] == "Fix #913"


def test_no_pick_is_filler():
    for p in picks.rank(live_picks(), limit=10):
        assert not re.match(r"(none|unavailable)", p["title"] + p["reason"], re.IGNORECASE)
        assert p["score"] >= picks.SCORE_FLOOR


def test_the_live_ledger_yields_an_operator_step_and_never_the_ban():
    text = nm.ROADMAP_STATUS.read_text(encoding="utf-8")
    assert picks.human_next_items(text), "the real ledger has no 'Exact next action (human)' items"
    steps = picks.operator_picks(text)
    assert steps and not picks.forbidden(steps[0]["prompt"] + steps[0]["reason"])


# --------------------------------------------------------------------------
# sources
# --------------------------------------------------------------------------


def test_operator_pick_is_the_first_actionable_human_step():
    [step] = picks.operator_picks(ROADMAP)
    assert step["title"] == "Phase L research" and step["kind"] == "operator"
    assert step["reason"] == "review strategy results and choose a question."
    assert picks.operator_picks(None) == []
    assert picks.operator_picks(ROADMAP.split("1. ")[0] + "1. **Hard ban:** no `auto_live`.\n") == []


def test_a_red_required_check_makes_a_pr_pick_and_the_newest_run_wins():
    rollup = green_rollup() + [run("Backend tests", "FAILURE", at="2026-10-14T02:00:00Z")]
    [pr] = picks.pr_picks([{"number": 7, "title": "feat: x", "statusCheckRollup": rollup}])
    assert pr["title"] == "Get PR #7 green" and "Backend tests failed" in pr["reason"]
    rerun = rollup + [run("Backend tests", "SUCCESS", at="2026-10-14T03:00:00Z")]
    assert picks.pr_picks([{"number": 7, "title": "x", "statusCheckRollup": rerun}]) == []


def test_pending_skipped_drafts_and_holds():
    pending = green_rollup() + [run("Frontend E2E", None, "IN_PROGRESS", "2026-10-14T02:00:00Z")]
    assert picks.pr_picks([{"number": 1, "title": "x", "statusCheckRollup": pending}]) == []
    skipped = [run(c, "SKIPPED") for c in picks.REQUIRED_CHECKS]
    assert picks.pr_picks([{"number": 2, "title": "x", "statusCheckRollup": skipped}])
    red = [run("Agent contract", "FAILURE")]
    assert picks.pr_picks([{"number": 3, "title": "x", "isDraft": True, "statusCheckRollup": red}]) == []
    held = {"number": 4, "title": "x", "labels": [{"name": "do-not-merge"}], "statusCheckRollup": red}
    assert picks.pr_picks([held]) == []


def test_a_conflicting_pr_ranks_below_a_p1():
    [pr] = picks.pr_picks([{"number": 5, "title": "x", "mergeable": "CONFLICTING",
                            "statusCheckRollup": green_rollup()}])
    assert pr["title"] == "Unblock PR #5" and pr["score"] < picks.SEVERITY_SCORE["P1"]


def test_backlog_picks_offer_batches_never_gated_claimed_or_decision_issues():
    live = nm.with_inbox(PACKAGES, ISSUES)
    titles = {p["title"]: p for p in picks.backlog_picks(live, ISSUES, HELD)}
    assert "Claim state-truth batch 0" in titles          # P1 #316 lives there
    assert titles["Claim state-truth batch 0"]["score"] == (
        picks.SEVERITY_SCORE["P1"] + picks.PLAN_NEXT_BONUS)  # and it is the plan's next batch
    assert "#316" in titles["Claim state-truth batch 0"]["reason"]
    assert {"Fix #913", "Fix #722"} <= set(titles)      # untriaged P1s, on their own
    assert not any(t in titles for t in ("Fix #315", "Fix #308", "Fix #331", "Claim recorder batch 0"))


def test_triage_pick_names_the_urgent_inbox_issues():
    [t] = picks.triage_pick(ISSUES)
    assert t["score"] == picks.SCORE_TRIAGE_URGENT and "#722, #913" in t["reason"]
    calm = [i for i in ISSUES if i["number"] == 927]
    assert picks.triage_pick(calm)[0]["score"] == picks.SCORE_TRIAGE_BASE + 1
    assert picks.triage_pick([i for i in ISSUES if not i["milestone"]]) == []


def test_decide_pick_is_the_gate_that_frees_the_most_and_a_p0_lifts_it():
    [d] = picks.decide_pick(PACKAGES, ISSUES)
    assert d["title"] == "Unblock #340" and "frees 3" in d["badge"]
    assert d["score"] == picks.SEVERITY_SCORE["P0"]       # P0 #315 waits on it
    assert d["reason"] == "#340 Phase 3: keep history_* as the single replay surface?"
    poisoned = [dict(PACKAGES[3], gate="#340 flip auto_live on for the replay?")]
    assert picks.decide_pick(poisoned, ISSUES) == []
    assert picks.decide_pick(PACKAGES[:3], ISSUES) == []


# --------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------


def test_rank_keeps_the_best_three_two_per_kind_and_withholds_forbidden_offers():
    cands = [picks.pick("fix", 90 - i, f"Fix #{i}", "r", "P1", "danger", "p") for i in range(4)]
    cands.append(picks.pick("triage", 50, "Triage", "r", "b", "warning", "p"))
    cands.append(picks.pick("operator", 99, "Go live now", "r", "b", "neutral", "p"))
    cands.append(picks.pick("decide", 39, "Low", "r", "b", "neutral", "p"))
    assert [p["title"] for p in picks.rank(cands)] == ["Fix #0", "Fix #1", "Triage"]


def test_the_agents_own_step_outranks_a_p1_but_not_a_p0():
    t = picks.thread_pick("Merge PR #9|CI is green.|Merge PR #9 and delete its branch.")
    assert picks.rank(calm_picks() + [t])[0] is t
    assert picks.rank(live_picks() + [t])[1] is t
    import pytest

    for bad in ("only a title", "a|b", "a||c"):
        with pytest.raises(ValueError):
            picks.thread_pick(bad)


def test_unreadable_sources_add_no_picks():
    only = picks.all_picks(roadmap_text=ROADMAP, packages=PACKAGES, issues=None, held=None, prs=None)
    assert [p["kind"] for p in only] == ["operator"]


# --------------------------------------------------------------------------
# rendering: the desktop card and the text menu agree
# --------------------------------------------------------------------------


def test_card_escapes_text_and_sends_the_prompt():
    p = picks.pick("fix", 85, "Fix <#1>", 'a "quoted" & <b> reason', "P1", "danger",
                   'Fix it: "now" & <today>')
    html = render.render_card([p, picks.pick("triage", 70, "Triage", "r", "b", "warning", "q")])
    assert "Fix &lt;#1&gt;" in html and "&lt;b&gt;" in html and "<b>" not in html
    assert 'data-prompt="Fix it: &quot;now&quot; &amp; &lt;today&gt;"' in html
    assert html.count('onclick="sendPrompt(this.dataset.prompt)"') == 2
    assert html.count('class="top"') == 1 and html.count("Recommended") == 1
    assert 'class="sr-only"' in html and "<!--" not in html
    assert render.render_card([]) == ""


def test_menu_passes_the_lint_and_stars_the_best_pick():
    menu = render.render_menu(picks.rank(calm_picks()))
    assert nm.lint(menu) == []
    assert menu.splitlines()[1].startswith("1. ★ **Fix #913** -- ")
    assert render.render_menu([]) == ""


def test_seed_lines_carry_scores_or_say_skip():
    lines = render.render_seed(picks.rank(calm_picks()), as_of="t", source="live")
    assert lines[0].startswith("Next-move picks (as of t, source=live")
    assert lines[1].startswith(f"1. [{picks.SEVERITY_SCORE['P1'] + picks.MONEY_PATH_BONUS}] Fix #913")
    assert "skip the menu" in render.render_seed([], as_of="t", source="live")[1]


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------


def test_offline_cli_never_touches_github(capsys, monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("gh must not be called offline")

    monkeypatch.setattr(nm, "fetch_issues", _boom)
    monkeypatch.setattr(nm, "run_gh", _boom)
    assert nm.main(["seed", "--offline"]) == 0
    assert "source=unavailable" in capsys.readouterr().out
    assert nm.main(["menu", "--offline", "--thread", "A|b|c"]) == 0
    assert "1. ★ **A** -- b" in capsys.readouterr().out


def test_collect_live_and_fetch_prs_fail_open_when_gh_is_unreachable(monkeypatch):
    def _down(*a, **kw):
        raise RuntimeError("gh failed")

    monkeypatch.setattr(nm, "fetch_issues", _down)
    monkeypatch.setattr(nm, "run_gh", _down)
    from datetime import datetime, timezone

    issues, held, known = nm.collect_live(budget=nm._Budget(1), now=datetime.now(timezone.utc))
    assert issues is None and held == {} and known is False
    assert nm.fetch_prs(budget=nm._Budget(1)) is None


def test_the_picks_agree_with_next_about_who_holds_a_batch(monkeypatch):
    """The picks decide whether a batch is held, so they resolve claims the way
    `next` does (claim-resolution R3): a claim past the TTL whose branch was
    committed minutes ago is still held, and the menu must not hand it out.
    """
    from datetime import datetime, timedelta, timezone

    from tools.backlog_claims import CLAIM_TTL_HOURS, format_claim

    now = datetime(2026, 9, 20, 15, tzinfo=timezone.utc)
    claimed_at = now - timedelta(hours=CLAIM_TTL_HOURS + 2)
    monkeypatch.setattr(nm, "fetch_issues", lambda **kw: [issue(7, labels=["claimed"])])
    monkeypatch.setattr(nm, "fetch_comments", lambda n, **kw: [
        {"body": format_claim(agent="worker-a", batch="s#0", branch="a/x", at=claimed_at),
         "createdAt": claimed_at.strftime("%Y-%m-%dT%H:%M:%SZ")}])

    monkeypatch.setattr(nm, "_branch_activity", lambda budget: (lambda ref: now - timedelta(days=3)))
    _issues, held, known = nm.collect_live(budget=nm._Budget(5), now=now)
    assert known is True and held == {}

    monkeypatch.setattr(nm, "_branch_activity", lambda budget: (lambda ref: now - timedelta(minutes=5)))
    _issues, held, known = nm.collect_live(budget=nm._Budget(5), now=now)
    assert known is True and set(held) == {7}, "a holder still committing must not be offered"


def test_an_exhausted_seed_budget_goes_offline_rather_than_guessing():
    # `last_commit_at` swallows OSError and TimeoutError is one.
    import pytest

    with pytest.raises(TimeoutError):
        nm._branch_activity(nm._Budget(0))("a/x")


# --------------------------------------------------------------------------
# lint
# --------------------------------------------------------------------------


def _rule_example() -> str:
    block = RULE.read_text(encoding="utf-8").split("## Example", 1)[1]
    return block.split("```text", 1)[1].split("```", 1)[0]


def test_rule_example_passes_the_lint():
    assert nm.lint(_rule_example()) == []


def test_lint_rejects_bad_shapes():
    good = _rule_example()
    assert any("forbidden" in p for p in nm.lint(good + "\nalso enable auto_live"))
    assert any("one star" in p for p in nm.lint(good.replace("★ ", "", 1)))
    assert any("one star" in p for p in nm.lint(good.replace("2. **", "2. ★ **", 1)))
    moved = good.replace("1. ★ **", "1. **", 1).replace("2. **", "2. ★ **", 1)
    assert any("on pick 1" in p for p in nm.lint(moved))
    assert any("retired lane" in p for p in nm.lint(good.replace("2. **", "2. `[ship]` **", 1)))
    assert any("filler" in p for p in nm.lint(good.replace("3. **", "3. none -- **", 1)))
    assert any("**Title** -- reason" in p for p in nm.lint(good.replace(" -- ", ": ", 1)))
    assert any("words (max" in p for p in nm.lint(good.replace("2. **", "2. **" + "w " * 45, 1)))
    assert any("picks (expected" in p for p in nm.lint(good + "4. **Four** -- too many\n"))
    assert any("missing" in p for p in nm.lint("just a reply with no menu"))


def test_lint_accepts_question_mode():
    question = "**Your call** (reply with a number; `0` = other):\n1. ★ Keep it. -- cheapest\n2. Cut it.\n"
    assert nm.lint(question) == []


# --------------------------------------------------------------------------
# single home: the constitution and the rule point at the tool
# --------------------------------------------------------------------------


def _footer_bullet() -> str:
    text = AGENTS.read_text(encoding="utf-8")
    start = text.index("**Next-move picks**")
    return text[start:text.index("\n", start)]


def test_agents_md_points_at_the_rule_and_the_tool_and_keeps_no_lanes():
    bullet = _footer_bullet()
    assert "next-move-footer.mdc" in bullet and "tools/next_moves.py" in bullet
    assert "card" in bullet and "menu" in bullet
    assert not nm.RETIRED_LANE_RE.search(AGENTS.read_text(encoding="utf-8"))


def test_rule_is_always_on_and_names_both_renderings():
    text = RULE.read_text(encoding="utf-8")
    assert "alwaysApply: true" in text
    assert "next_moves.py card" in text and "next_moves.py menu" in text
    assert not nm.RETIRED_LANE_RE.search(text)


def test_ci_runs_this_file():
    assert "tools/test_next_moves.py" in DEPLOY.read_text(encoding="utf-8")


def test_offline_cli_emits_utf8_with_legacy_windows_pipe_encoding():
    import os
    import subprocess

    result = subprocess.run(
        [sys.executable, str(nm.REPO_ROOT / "tools" / "next_moves.py"), "menu", "--offline",
         "--thread", "Fix it|a reason · with a middle dot|do it"],
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert "1. ★ **Fix it** -- a reason · with a middle dot" in result.stdout.decode("utf-8")
