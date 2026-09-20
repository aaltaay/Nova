"""Contract tests for backlog triage (packages = milestones, gaps, Map splice)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.backlog_triage import (
    MAP_BEGIN,
    MAP_END,
    NO_MILESTONE,
    PACKAGES_PATH,
    READY,
    analyse,
    duplicate_aliases,
    hygiene_gaps,
    load_packages,
    milestone_description,
    milestone_title,
    next_pr,
    pick_next,
    plan_drift,
    render_map_section,
    render_next,
    render_report,
    rollup,
    severity_of,
    splice_map,
)

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "backlog-triage.yml"
BACKLOG = REPO_ROOT / "BACKLOG.md"


def issue(number, *, labels=(), milestone=None, title=None):
    return {
        "number": number,
        "title": title or f"issue {number}",
        "labels": [{"name": name} for name in labels],
        "milestone": {"title": milestone, "number": 1} if milestone else None,
        "url": f"https://github.com/aaltaay/Nova/issues/{number}",
    }


FULL = ("deferred", "P1", "bug", "domain:market-feed")


# --------------------------------------------------------------------------
# field extraction
# --------------------------------------------------------------------------


def test_milestone_title_falls_back_to_no_package():
    assert milestone_title(issue(1)) == NO_MILESTONE
    assert milestone_title(issue(1, milestone="01 - recorder")) == "01 - recorder"


def test_severity_picks_the_most_severe_label_present():
    assert severity_of(issue(1, labels=("P2", "P0"))) == "P0"
    assert severity_of(issue(1, labels=("bug",))) == ""


# --------------------------------------------------------------------------
# hygiene
# --------------------------------------------------------------------------


def test_fully_labelled_packaged_issue_has_no_gaps():
    assert hygiene_gaps(issue(1, labels=FULL, milestone="01 - recorder")) == []


def test_missing_package_is_reported_first():
    gaps = hygiene_gaps(issue(1, labels=FULL))
    assert gaps[0] == "no-package"


def test_every_missing_field_is_named():
    gaps = hygiene_gaps(issue(276))
    assert set(gaps) == {"no-package", "no-priority", "no-kind", "no-domain", "no-deferred"}


def test_missing_deferred_label_is_a_gap_even_when_otherwise_complete():
    # deferred_log.py status is what agents consult before any fix; an issue
    # without the label is invisible there.
    gaps = hygiene_gaps(issue(1, labels=("P1", "bug", "domain:ui"), milestone="01 - recorder"))
    assert gaps == ["no-deferred"]


# --------------------------------------------------------------------------
# rollup
# --------------------------------------------------------------------------


def test_rollup_counts_by_package_and_severity():
    data = rollup(
        [
            issue(1, labels=("P0", "bug"), milestone="01 - recorder"),
            issue(2, labels=("P1", "bug"), milestone="01 - recorder"),
            issue(3, labels=("P2", "bug"), milestone="02 - replay"),
        ]
    )
    assert data["01 - recorder"]["open"] == 2
    assert data["01 - recorder"]["P0"] == 1
    assert data["01 - recorder"]["numbers"] == [1, 2]
    assert data["02 - replay"]["P2"] == 1


def test_rollup_counts_unprioritised_separately():
    data = rollup([issue(1, labels=("bug",), milestone="01 - recorder")])
    assert data["01 - recorder"]["unprioritised"] == 1


def test_unpackaged_issues_land_in_their_own_bucket():
    data = rollup([issue(9, labels=("P3",))])
    assert data[NO_MILESTONE]["open"] == 1


def test_package_order_follows_authored_rank_not_alphabet():
    packages = [
        {"rank": 2, "slug": "b", "title": "02 - replay", "issues": [], "readiness": READY},
        {"rank": 1, "slug": "a", "title": "01 - recorder", "issues": [], "readiness": READY},
    ]
    data = analyse([], [], packages)
    assert data["package_order"] == ["01 - recorder", "02 - replay"]


# --------------------------------------------------------------------------
# legacy alias collisions
# --------------------------------------------------------------------------


def test_duplicate_d_aliases_are_reported():
    dupes = duplicate_aliases(
        [
            issue(337, title="D-073 -- capture fidelity"),
            issue(326, title="D-073 -- flaky cancel"),
            issue(315, title="D-064 -- recorder"),
        ]
    )
    assert dupes == {"D-073": [326, 337]}


def test_unique_alias_is_not_reported():
    assert duplicate_aliases([issue(315, title="D-064 -- recorder")]) == {}


# --------------------------------------------------------------------------
# analyse + render
# --------------------------------------------------------------------------


def sample():
    issues = [
        issue(315, labels=("deferred", "P0", "bug", "domain:market-feed"), milestone="01 - recorder"),
        issue(276),
    ]
    milestones = [
        {"title": "01 - recorder", "state": "open", "number": 1},
        {"title": "02 - empty", "state": "open", "number": 2},
    ]
    return issues, milestones


def test_analyse_flags_unpackaged_and_empty_packages():
    data = analyse(*sample())
    assert data["unpackaged"] == [276]
    assert data["empty_packages"] == ["02 - empty"]
    assert 276 in data["hygiene_gaps"]
    assert 315 not in data["hygiene_gaps"]


def test_report_names_the_empty_milestone_as_closable():
    text = render_report(analyse(*sample()))
    assert "02 - empty" in text
    assert "milestone can be closed" in text


def test_report_says_clean_when_there_are_no_gaps():
    issues = [issue(315, labels=FULL, milestone="01 - recorder")]
    text = render_report(analyse(issues, [{"title": "01 - recorder", "state": "open", "number": 1}]))
    assert "Hygiene: clean" in text


def test_map_section_links_milestones_and_lists_the_triage_queue():
    issues, milestones = sample()
    section = render_map_section(analyse(issues, milestones), milestones, [])
    assert section.startswith(MAP_BEGIN)
    assert section.endswith(MAP_END)
    assert "/milestone/1" in section
    assert "#315" in section
    assert "Triage queue" in section
    assert "no-package" in section


# --------------------------------------------------------------------------
# splice -- hand-written prose outside the markers must survive
# --------------------------------------------------------------------------


def test_splice_replaces_only_the_generated_block():
    body = f"Intro prose.\n\n{MAP_BEGIN}\nOLD\n{MAP_END}\n\nTrailing runbook."
    out = splice_map(body, f"{MAP_BEGIN}\nNEW\n{MAP_END}")
    assert "Intro prose." in out
    assert "Trailing runbook." in out
    assert "OLD" not in out
    assert "NEW" in out


def test_splice_appends_when_markers_are_absent():
    out = splice_map("Just prose.", f"{MAP_BEGIN}\nNEW\n{MAP_END}")
    assert out.startswith("Just prose.")
    assert MAP_BEGIN in out


def test_splice_into_empty_body_does_not_leave_leading_blank_lines():
    out = splice_map("", f"{MAP_BEGIN}\nNEW\n{MAP_END}")
    assert out.startswith(MAP_BEGIN)


def test_splice_is_idempotent():
    section = f"{MAP_BEGIN}\nNEW\n{MAP_END}"
    once = splice_map("Intro.", section)
    assert splice_map(once, section) == once


# --------------------------------------------------------------------------
# wiring -- the periodic path must actually exist
# --------------------------------------------------------------------------


def test_backlog_md_exists_and_points_at_the_triage_command():
    assert BACKLOG.exists(), "BACKLOG.md is the narrative home for the packages"
    text = BACKLOG.read_text(encoding="utf-8")
    assert "backlog_triage.py" in text


def test_scheduled_workflow_runs_triage_on_a_cron():
    assert WORKFLOW.exists(), "periodic triage needs a scheduled workflow"
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "schedule:" in text
    assert "cron:" in text
    assert "workflow_dispatch:" in text
    assert "backlog_triage.py" in text


# --------------------------------------------------------------------------
# plan drift -- the authored file vs what GitHub actually says
# --------------------------------------------------------------------------


PKGS = [
    {"rank": 1, "slug": "a", "title": "01 - a", "issues": [1, 2], "readiness": READY,
     "objective": "o", "done": ["d"], "gate": "",
     "prs": [{"title": "pr a", "issues": [1, 2], "note": "n", "gated": False}]},
    {"rank": 2, "slug": "b", "title": "02 - b", "issues": [3], "readiness": "needs-decision-first",
     "objective": "o", "done": ["d"], "gate": "operator must choose X",
     "prs": [{"title": "pr b", "issues": [3], "note": "GATED", "gated": True}]},
]


def test_drift_is_silent_when_milestones_match_the_plan():
    issues = [issue(1, milestone="01 - a"), issue(2, milestone="01 - a")]
    assert plan_drift(PKGS, issues) == []


def test_drift_reports_a_wrong_milestone():
    problems = plan_drift(PKGS, [issue(1, milestone="02 - b")])
    assert len(problems) == 1
    assert "#1" in problems[0] and "run sync" in problems[0]


def test_drift_reports_an_open_issue_that_is_in_no_package():
    problems = plan_drift(PKGS, [issue(99, milestone="01 - a")])
    assert any("#99" in p and "no package" in p for p in problems)


def test_drift_ignores_closed_issues_still_listed_in_the_plan():
    # #2 is in the plan but absent from the open list: that is completed work.
    assert plan_drift(PKGS, [issue(1, milestone="01 - a")]) == []


def test_drift_catches_an_issue_placed_in_two_packages():
    dupe = PKGS + [{"rank": 3, "slug": "c", "title": "03 - c", "issues": [1],
                    "readiness": READY, "objective": "o", "done": [], "gate": "", "prs": []}]
    assert any("two packages" in p for p in plan_drift(dupe, []))


# --------------------------------------------------------------------------
# "what do I work on next?"
# --------------------------------------------------------------------------


def test_next_picks_the_highest_ranked_startable_package():
    pkg, skipped = pick_next(PKGS, {1, 2, 3})
    assert pkg["slug"] == "a"
    assert skipped == []


def test_next_skips_a_package_with_nothing_open_left():
    pkg, _ = pick_next(PKGS, {3})
    assert pkg is None, "02 - b is gated, so nothing is startable"


def test_next_skips_gated_packages_but_returns_them_for_surfacing():
    ranked_gate_first = [dict(PKGS[1], rank=1), dict(PKGS[0], rank=2)]
    pkg, skipped = pick_next(ranked_gate_first, {1, 2, 3})
    assert pkg["slug"] == "a"
    assert [s["slug"] for s in skipped] == ["b"], "the gate must not be hidden"


def test_next_pr_returns_the_first_ungated_batch_with_open_issues():
    pkg = {"prs": [
        {"title": "done", "issues": [1], "note": "n", "gated": False},
        {"title": "live", "issues": [2, 3], "note": "n", "gated": False},
    ]}
    assert next_pr(pkg, {2, 3})["title"] == "live"


def test_next_pr_never_returns_a_gated_batch():
    pkg = {"prs": [{"title": "blocked", "issues": [1], "note": "GATED", "gated": True}]}
    assert next_pr(pkg, {1}) is None


def test_render_next_states_the_package_the_pr_and_the_done_criteria():
    pkg, skipped = pick_next(PKGS, {1, 2, 3})
    text = render_next(pkg, next_pr(pkg, {1, 2}), skipped, {1, 2}, {1: "first", 2: "second"})
    assert "NEXT: 01 - a" in text
    assert "#1" in text and "#2" in text
    assert "pr a" in text
    assert "Package is done when:" in text
    assert "origin/master" in text


def test_render_next_explains_itself_when_only_gated_work_remains():
    text = render_next(None, None, [PKGS[1]], {3}, {})
    assert "gated or already claimed" in text
    assert "operator must choose X" in text


# --------------------------------------------------------------------------
# the real authored plan must stay valid
# --------------------------------------------------------------------------


def test_real_packages_file_loads_and_is_rank_ordered():
    packages = load_packages()
    assert packages, "backlog-packages.json must define packages"
    ranks = [p["rank"] for p in packages]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(ranks), "two packages may not share a rank"


def test_real_packages_assign_every_issue_exactly_once():
    seen = [n for p in load_packages() for n in p["issues"]]
    assert len(seen) == len(set(seen)), "an issue may not be in two packages"


def test_real_package_prs_cover_every_issue_in_their_package():
    for pkg in load_packages():
        covered = sorted(n for pr in pkg["prs"] for n in pr["issues"])
        assert covered == sorted(pkg["issues"]), f"{pkg['slug']} has issues in no PR"


def test_real_packages_have_verifiable_done_criteria():
    for pkg in load_packages():
        assert pkg["done"], f"{pkg['slug']} has no definition of done"
        for line in pkg["done"]:
            assert len(line) > 25, f"{pkg['slug']} has a stub done criterion: {line!r}"


def test_a_gated_package_names_its_gate():
    for pkg in load_packages():
        if pkg["readiness"] != READY:
            assert pkg["gate"], f"{pkg['slug']} is not ready but names no gate"


def test_at_least_one_package_is_startable_right_now():
    # If this ever fails the backlog is fully decision-blocked, which is a
    # real finding, not a test bug.
    pkg, _ = pick_next(load_packages(), {n for p in load_packages() for n in p["issues"]})
    assert pkg is not None


def test_milestone_description_carries_objective_gate_and_done():
    pkg = load_packages()[0]
    text = milestone_description(pkg)
    assert pkg["objective"] in text
    assert "Done when:" in text
    assert "backlog_triage.py next" in text


def test_packages_file_declares_owner_and_invalidation():
    # persisted-state.mdc: a cache file needs an owner and an invalidation rule.
    import json as _json
    raw = _json.loads(PACKAGES_PATH.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert "backlog_triage" in raw["owner"]
    assert raw["invalidation"]


def test_the_backlog_map_issue_is_not_itself_backlog_work():
    from tools.backlog_triage import META_LABEL, is_meta
    assert is_meta(issue(361, labels=(META_LABEL, "documentation")))
    assert not is_meta(issue(314, labels=FULL))


# --------------------------------------------------------------------------
# the inbox -- new issues are queued, never invisible, never auto-routed
# --------------------------------------------------------------------------


from tools.backlog_triage import (  # noqa: E402
    INBOX_TITLE,
    URGENT,
    candidate_packages,
    domain_labels,
    render_triage,
)

INBOX_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "backlog-inbox.yml"


def inboxed(number, *, labels=()):
    return issue(number, labels=tuple(labels) + ("deferred",), milestone=INBOX_TITLE)


def test_an_inbox_issue_is_queued_not_drift():
    # It has a milestone, so it is visible everywhere; it is just not routed.
    assert plan_drift(PKGS, [inboxed(500, labels=("P2", "bug", "domain:ui"))]) == []


def test_an_issue_with_no_milestone_at_all_is_still_drift():
    # That means the inbox workflow failed; it must not be silently tolerated.
    problems = plan_drift(PKGS, [issue(500, labels=("P2", "bug", "domain:ui", "deferred"))])
    assert any("#500" in p and "no package" in p for p in problems)


def test_inbox_issues_are_reported_separately():
    data = analyse([inboxed(500, labels=("P2", "bug", "domain:ui"))], [], PKGS)
    assert data["inbox"] == [500]
    assert data["inbox_urgent"] == []


def test_an_untriaged_p0_is_flagged_urgent():
    data = analyse([inboxed(501, labels=("P0", "bug", "domain:ui"))], [], PKGS)
    assert data["inbox_urgent"] == [501]


def test_report_surfaces_the_inbox_and_names_the_triage_command():
    text = render_report(analyse([inboxed(500, labels=("P2", "bug", "domain:ui"))], [], PKGS))
    assert "Inbox: 1 awaiting routing" in text
    assert "backlog_triage.py triage" in text


def test_report_marks_an_urgent_inbox_issue():
    text = render_report(analyse([inboxed(501, labels=("P1", "bug", "domain:ui"))], [], PKGS))
    assert "URGENT" in text and "#501" in text


def test_an_inbox_issue_does_not_count_as_a_hygiene_gap():
    # It has a package (the inbox) and full labels; it needs routing, not fields.
    assert hygiene_gaps(inboxed(500, labels=("P2", "bug", "domain:ui"))) == []


# --- routing suggestions are suggestions ---------------------------------


def test_candidate_packages_ranks_by_shared_domain_labels():
    by_number = {
        1: issue(1, labels=("domain:ui",)),
        2: issue(2, labels=("domain:ui",)),
        3: issue(3, labels=("domain:market-feed",)),
    }
    pkgs = [
        {"title": "01 - a", "slug": "a", "issues": [1, 2]},
        {"title": "02 - b", "slug": "b", "issues": [3]},
    ]
    hits = candidate_packages(issue(9, labels=("domain:ui",)), pkgs, by_number)
    assert hits[0] == ("a", 2)
    assert [s for s, _ in hits] == ["a"]


def test_candidate_packages_never_suggests_the_inbox_itself():
    by_number = {1: issue(1, labels=("domain:ui",))}
    pkgs = [{"title": INBOX_TITLE, "slug": "untriaged", "issues": [1]}]
    assert candidate_packages(issue(9, labels=("domain:ui",)), pkgs, by_number) == []


def test_an_issue_with_no_domain_label_gets_no_suggestion():
    assert candidate_packages(issue(9, labels=("P2",)), [], {}) == []


def test_domain_labels_ignores_priority_and_kind():
    assert domain_labels(issue(1, labels=("P1", "bug", "domain:ui"))) == {"domain:ui"}


def test_triage_output_marks_suggestions_as_suggestions_only():
    by_number = {1: issue(1, labels=("domain:ui",))}
    pkgs = [{"title": "01 - a", "slug": "a", "issues": [1]}]
    text = render_triage([inboxed(500, labels=("P2", "bug", "domain:ui"))], pkgs, by_number)
    assert "suggestion only" in text, "routing must never read as an assignment"
    assert "#500" in text


def test_triage_output_calls_out_urgent_issues():
    text = render_triage([inboxed(501, labels=("P0", "bug", "domain:ui"))], [], {})
    assert "URGENT" in text


def test_triage_says_so_when_the_inbox_is_empty():
    assert "Inbox empty" in render_triage([], [], {})


# --- the inbox must exist as a real package ------------------------------


def test_the_inbox_package_exists_and_is_never_startable():
    packages = load_packages()
    inbox = [p for p in packages if p["title"] == INBOX_TITLE]
    assert inbox, "the inbox package must exist or the workflow cannot assign it"
    assert inbox[0]["readiness"] != READY, "next must never hand out unrouted work"
    assert packages[0]["title"] == INBOX_TITLE, "the inbox sorts first so it is always seen"


def test_working_packages_are_still_ranked_one_upwards():
    ranks = [p["rank"] for p in load_packages()]
    assert ranks[0] == 0, "the inbox is rank 0"
    assert ranks[1:] == list(range(1, len(ranks))), "working packages are a strict 1..N"


def test_next_skips_the_inbox_but_surfaces_it():
    from tools.backlog_triage import with_inbox
    real = load_packages()[1]
    # An unrouted issue plus one real package's work.
    packages = with_inbox(load_packages(), [inboxed(500, labels=("P2", "bug", "domain:ui"))])
    pkg, skipped = pick_next(packages, {500} | set(real["issues"]))
    assert pkg["title"] != INBOX_TITLE
    assert any(s["title"] == INBOX_TITLE for s in skipped)


def test_urgent_severities_are_the_ones_that_break_a_desk():
    assert set(URGENT) == {"P0", "P1"}


def test_inbox_workflow_assigns_on_open_and_does_not_guess_a_package():
    assert INBOX_WORKFLOW.exists()
    text = INBOX_WORKFLOW.read_text(encoding="utf-8")
    assert "issues:" in text and "opened" in text
    assert INBOX_TITLE in text
    assert "already in" in text, "must not overwrite a milestone the filer set"


def test_with_inbox_reads_membership_from_the_milestone_not_the_json():
    from tools.backlog_triage import with_inbox
    packages = with_inbox(
        [{"title": INBOX_TITLE, "slug": "untriaged", "issues": [], "readiness": "needs-triage"}],
        [inboxed(500), inboxed(501), issue(9, milestone="01 - a")],
    )
    assert packages[0]["issues"] == [500, 501]


def test_with_inbox_leaves_real_packages_untouched():
    from tools.backlog_triage import with_inbox
    original = {"title": "01 - a", "slug": "a", "issues": [1, 2], "readiness": READY}
    assert with_inbox([original], [inboxed(500)])[0]["issues"] == [1, 2]


def test_an_empty_inbox_is_never_advertised_as_closable():
    packages = [{"rank": 0, "slug": "untriaged", "title": INBOX_TITLE,
                 "issues": [], "readiness": "needs-triage"}]
    data = analyse([], [{"title": INBOX_TITLE, "state": "open", "number": 1}], packages)
    assert data["empty_packages"] == [], "the inbox is permanent"
    text = render_report(data)
    assert "milestone can be closed" not in text
    assert "nothing awaiting triage" in text


# --------------------------------------------------------------------------
# claims -- cross-tool advisory locking on a PR batch
# --------------------------------------------------------------------------


from datetime import datetime, timedelta, timezone  # noqa: E402

from tools.backlog_triage import (  # noqa: E402
    CLAIM_LABEL,
    CLAIM_TTL_HOURS,
    active_claim,
    batch_ref,
    format_claim,
    format_release,
    parse_claim,
    resolve_batch,
)

NOW = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)


def comment(body, *, at):
    return {"body": body, "createdAt": at.strftime("%Y-%m-%dT%H:%M:%SZ")}


def claim_comment(*, agent="codex@laptop", batch="recorder-safety#0", branch="agent/x", at=NOW):
    return comment(format_claim(agent=agent, batch=batch, branch=branch, at=at), at=at)


# --- round trip -----------------------------------------------------------


def test_a_claim_round_trips_through_its_comment():
    fields = parse_claim(format_claim(
        agent="cursor@desk", batch="test-integrity#0", branch="agent/ti", at=NOW))
    assert fields["agent"] == "cursor@desk"
    assert fields["batch"] == "test-integrity#0"
    assert fields["branch"] == "agent/ti"
    assert fields["at"] == "2026-09-20T12:00:00Z"


def test_a_claim_comment_is_human_readable_too():
    body = format_claim(agent="a", batch="b#0", branch="c", at=NOW)
    assert "Claimed by" in body, "a human reading the issue must understand it"
    assert str(CLAIM_TTL_HOURS) in body


def test_parse_claim_ignores_an_ordinary_comment():
    assert parse_claim("just a normal comment about the bug") is None


# --- what is in force -----------------------------------------------------


def test_a_fresh_claim_is_in_force():
    claim = active_claim([claim_comment()], now=NOW + timedelta(hours=1))
    assert claim is not None
    assert claim["stale"] is False
    assert claim["agent"] == "codex@laptop"


def test_a_claim_past_the_ttl_is_stale_not_hidden():
    claim = active_claim([claim_comment()], now=NOW + timedelta(hours=CLAIM_TTL_HOURS + 1))
    assert claim is not None, "a stale claim must still be reportable, not vanish"
    assert claim["stale"] is True


def test_a_claim_just_inside_the_ttl_still_holds():
    claim = active_claim([claim_comment()], now=NOW + timedelta(hours=CLAIM_TTL_HOURS) - timedelta(minutes=1))
    assert claim["stale"] is False


def test_a_release_after_a_claim_clears_it():
    comments = [
        claim_comment(at=NOW),
        comment(format_release(agent="codex@laptop", batch="recorder-safety#0"),
                at=NOW + timedelta(minutes=5)),
    ]
    assert active_claim(comments, now=NOW + timedelta(minutes=10)) is None


def test_a_reclaim_after_a_release_holds_again():
    comments = [
        claim_comment(agent="a", at=NOW),
        comment(format_release(agent="a", batch="x#0"), at=NOW + timedelta(minutes=5)),
        claim_comment(agent="b", at=NOW + timedelta(minutes=10)),
    ]
    claim = active_claim(comments, now=NOW + timedelta(minutes=20))
    assert claim["agent"] == "b"


def test_the_newest_marker_wins_regardless_of_list_order():
    comments = [
        comment(format_release(agent="a", batch="x#0"), at=NOW + timedelta(minutes=5)),
        claim_comment(agent="a", at=NOW),
    ]
    assert active_claim(comments, now=NOW + timedelta(minutes=10)) is None


def test_no_comments_means_no_claim():
    assert active_claim([], now=NOW) is None


def test_age_is_reported_for_the_holder():
    claim = active_claim([claim_comment()], now=NOW + timedelta(hours=2))
    assert claim["age_hours"] == 2.0


# --- next honours claims --------------------------------------------------


CLAIM_PKGS = [
    {"rank": 1, "slug": "a", "title": "01 - a", "issues": [1, 2, 3], "readiness": READY,
     "objective": "o", "done": ["d"], "gate": "",
     "prs": [
         {"title": "batch one", "issues": [1, 2], "note": "n", "gated": False},
         {"title": "batch two", "issues": [3], "note": "n", "gated": False},
     ]},
    {"rank": 2, "slug": "b", "title": "02 - b", "issues": [4], "readiness": READY,
     "objective": "o", "done": ["d"], "gate": "",
     "prs": [{"title": "batch b", "issues": [4], "note": "n", "gated": False}]},
]


def test_a_claimed_batch_is_skipped_for_the_next_one_in_the_same_package():
    pr = next_pr(CLAIM_PKGS[0], {1, 2, 3}, claimed={1})
    assert pr["title"] == "batch two", "a partially-claimed batch is not startable"


def test_claiming_any_issue_blocks_the_whole_batch():
    # The batch is one PR; holding half of it is holding all of it.
    assert next_pr(CLAIM_PKGS[0], {1, 2}, claimed={2}) is None


def test_a_fully_claimed_package_hands_the_agent_the_next_package():
    pkg, skipped = pick_next(CLAIM_PKGS, {1, 2, 3, 4}, claimed={1, 3})
    assert pkg["slug"] == "b", "two agents must fan out, not collide"
    assert skipped[0]["_skip_reason"] == "every startable batch is already claimed"


def test_render_next_says_why_a_package_was_skipped_for_a_claim():
    pkg, skipped = pick_next(CLAIM_PKGS, {1, 2, 3, 4}, claimed={1, 3})
    text = render_next(pkg, next_pr(pkg, {4}, {1, 3}), skipped, {4}, {4: "t"})
    assert "already claimed" in text


def test_no_claims_behaves_exactly_as_before():
    pkg, skipped = pick_next(CLAIM_PKGS, {1, 2, 3, 4})
    assert pkg["slug"] == "a" and skipped == []


# --- batch addressing -----------------------------------------------------


def test_batch_ref_is_stable_and_readable():
    assert batch_ref("recorder-safety", 0) == "recorder-safety#0"


def test_resolve_batch_defaults_to_the_first():
    index, batch = resolve_batch(CLAIM_PKGS[0], None)
    assert index == 0 and batch["title"] == "batch one"


def test_resolve_batch_rejects_an_out_of_range_index():
    import pytest
    with pytest.raises(RuntimeError, match="out of range"):
        resolve_batch(CLAIM_PKGS[0], 9)


def test_resolve_batch_rejects_a_package_with_no_batches():
    import pytest
    with pytest.raises(RuntimeError, match="no PR batches"):
        resolve_batch({"slug": "untriaged", "prs": []}, None)


def test_the_inbox_cannot_be_claimed():
    import pytest
    inbox = [p for p in load_packages() if p["title"] == INBOX_TITLE][0]
    with pytest.raises(RuntimeError, match="no PR batches"):
        resolve_batch(inbox, None)


def test_claim_label_is_a_single_known_name():
    # next uses the label as its cheap filter; a typo would silently
    # disable claim-awareness rather than fail loudly.
    assert CLAIM_LABEL == "claimed"


def test_backlog_md_documents_the_claim_protocol_and_its_limit():
    text = BACKLOG.read_text(encoding="utf-8")
    assert "claim --package" in text
    assert "advisory locking, not mutual exclusion" in text.lower()
    assert str(CLAIM_TTL_HOURS) in text, "the TTL must be documented, not folklore"


def test_wave_runner_tells_its_agents_to_claim_first():
    runner = REPO_ROOT / ".claude" / "workflows" / "backlog-wave.js"
    text = runner.read_text(encoding="utf-8")
    assert "backlog_triage.py claim" in text
    assert "backlog_triage.py release" in text
    assert "Do not use --force" in text, "a wave agent must never steal a live claim"
