"""The claim-resolution rules R1-R5, as a table over the whole state space.

Three consecutive patches to `active_claim` each fixed one scenario and broke
another -- the label outliving a withdrawal, a loser's release erasing the
winner, an abandoned claim outranking a fresh reclaim. Every one was a
combination of (agents x claim/release x fresh/stale) the previous patch had
not enumerated. So the combinations are enumerated here rather than discovered
one regression at a time.

Change this table before changing the rules it pins: an edit to
`backlog_claims` that this file still passes has not been reasoned about.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.backlog_claims import (
    CLAIM_TTL_HOURS,
    active_claim,
    claim_for,
    format_claim,
    format_release,
)

NOW = datetime(2026, 9, 20, 15, tzinfo=timezone.utc)
FRESH = NOW - timedelta(minutes=5)
OLD = NOW - timedelta(hours=CLAIM_TTL_HOURS + 2)
OLDER = NOW - timedelta(hours=CLAIM_TTL_HOURS + 6)

LEGACY_RELEASE = "<!-- nova-claim-release -->\nReleased by `someone`."


def claim(agent, at, *, batch="s#0", branch=None):
    return (at, format_claim(agent=agent, batch=batch,
                             branch=branch or f"{agent}/x", at=at))


def release(agent, at, *, batch="s#0"):
    return (at, format_release(agent=agent, batch=batch))


def legacy(at):
    return (at, LEGACY_RELEASE)


def comments(*rows):
    return [{"body": body, "createdAt": at.strftime("%Y-%m-%dT%H:%M:%SZ")}
            for at, body in rows]


# (id, markers, expected holder agent or None, expected stale)
TABLE = [
    # -- R1: an agent holds while their own newest marker is a claim ---------
    ("nothing",                   [],                                     None,       None),
    ("one fresh claim",           [claim("a", FRESH)],                    "a",        False),
    ("one expired claim",         [claim("a", OLD)],                      "a",        True),
    ("claim then own release",    [claim("a", FRESH), release("a", NOW)], None,       None),
    ("release with no claim",     [release("a", NOW)],                    None,       None),
    ("reclaim after own release",
     [claim("a", OLD), release("a", OLD), claim("a", FRESH)],             "a",        False),

    # -- R1: one agent's release never speaks for another -------------------
    ("loser yields, winner holds",
     [claim("a", FRESH), claim("b", NOW), release("b", NOW)],             "a",        False),
    ("winner yields, loser holds",
     [claim("a", FRESH), claim("b", NOW), release("a", NOW)],             "b",        False),
    ("both yield",
     [claim("a", FRESH), claim("b", NOW), release("a", NOW), release("b", NOW)],
     None, None),

    # -- R2: a release naming nobody still clears everything before it -------
    ("legacy release clears all",  [claim("a", FRESH), legacy(NOW)],      None,       None),
    ("legacy release, then a claim",
     [claim("a", OLD), legacy(OLD), claim("b", FRESH)],                   "b",        False),

    # -- R4: earliest LIVE holder wins, stale only as a fallback -------------
    ("two live, earliest wins",
     [claim("a", FRESH), claim("b", NOW)],                                "a",        False),
    ("abandoned loses to fresh reclaim",
     [claim("a", OLD), claim("b", FRESH)],                                "b",        False),
    ("all expired, earliest reported",
     [claim("a", OLDER), claim("b", OLD)],                                "a",        True),
]


@pytest.mark.parametrize("label,rows,agent,stale",
                         TABLE, ids=[row[0] for row in TABLE])
def test_resolution_table(label, rows, agent, stale):
    held = active_claim(comments(*rows), now=NOW)
    if agent is None:
        assert held is None
        return
    assert held is not None, f"{label}: expected {agent} to hold"
    assert held["agent"] == agent
    assert held["stale"] is stale


# -- R3: branch activity revives a hold, never ends one ---------------------

ACTIVITY = [
    ("expired claim, branch just committed", OLD, NOW - timedelta(minutes=5), False),
    ("expired claim, branch also abandoned", OLD, OLDER,                      True),
    ("expired claim, branch unreadable",     OLD, None,                       True),
    ("live claim, branch long idle",         FRESH, OLDER,                    False),
]


@pytest.mark.parametrize("label,at,activity,stale", ACTIVITY,
                         ids=[row[0] for row in ACTIVITY])
def test_branch_activity_only_revives(label, at, activity, stale):
    held = active_claim(comments(claim("a", at)), now=NOW,
                        branch_activity_for=lambda ref: activity)
    assert held["stale"] is stale, label


def test_a_live_holder_never_costs_a_branch_lookup():
    # R3's affordability: this is why resolution can sit on `next`'s path.
    asked: list[str] = []
    active_claim(comments(claim("a", FRESH)), now=NOW,
                 branch_activity_for=lambda ref: asked.append(ref))
    assert asked == []


def test_only_the_elected_holders_branch_is_consulted():
    asked: list[str] = []
    active_claim(comments(claim("a", OLD), claim("b", OLD)), now=NOW,
                 branch_activity_for=lambda ref: asked.append(ref) or None)
    assert set(asked) <= {"a/x", "b/x"}


# -- R5: "which claim is mine" is its own question --------------------------


def test_claim_for_returns_the_asking_agents_claim():
    rows = comments(claim("a", FRESH, branch="a/keep"),
                    claim("b", NOW, branch="b/keep"))
    # The election returns a; b asking about itself must still get b.
    assert active_claim(rows, now=NOW)["agent"] == "a"
    assert claim_for(rows, agent="b")["branch"] == "b/keep"
    assert claim_for(rows, agent="a")["branch"] == "a/keep"


def test_claim_for_fails_closed():
    rows = comments(claim("a", FRESH))
    assert claim_for(rows, agent="nobody") is None
    assert claim_for(comments(claim("a", FRESH), release("a", NOW)), agent="a") is None
    assert claim_for(rows, agent="a", batch="other#9") is None


# -- the rule and the code cannot drift apart ------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
RULE = REPO_ROOT / ".cursor" / "rules" / "claim-resolution.mdc"
MODULE = REPO_ROOT / "tools" / "backlog_claims.py"


def test_the_rule_states_every_numbered_rule():
    # A rule file that has lost a rule governs less than it claims to.
    text = RULE.read_text(encoding="utf-8")
    for rule in ("R1", "R2", "R3", "R4", "R5"):
        assert f"**{rule}" in text, f"{rule} is missing from claim-resolution.mdc"


def test_the_rule_is_scoped_to_the_code_it_governs():
    head = RULE.read_text(encoding="utf-8").split("---")[1]
    assert "tools/backlog_claims.py" in head, "an unscoped rule attaches to nothing"


def test_the_code_points_at_the_rule_rather_than_restating_it():
    # Prose duplicated beside code is how a rule and its behaviour drift --
    # which is the defect that started this whole subsystem's trouble.
    text = MODULE.read_text(encoding="utf-8")
    assert "claim-resolution.mdc" in text
    assert "R1  Markers are per agent" not in text, (
        "the rules belong in the MDC rule, not copied back into the module"
    )


def test_the_rule_names_its_own_enforcement():
    assert "test_backlog_claims_table.py" in RULE.read_text(encoding="utf-8"), (
        "a rule with no executable form is decoration"
    )
