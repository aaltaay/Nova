"""The no-force-push ruleset's policy and its check (AGENTS.md section 5.1; owner, 2026-10-14)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools import no_force_push as nfp  # noqa: E402


def live(**over):
    """GET /rulesets/{id} as GitHub answered it on 2026-10-14 (ruleset 25104014), with ``over`` applied."""
    ruleset = {"id": 25104014, "name": "No force-push", "target": "branch", "enforcement": "active",
               "bypass_actors": [], "conditions": {"ref_name": {"include": ["~ALL"], "exclude": []}},
               "rules": [{"type": "non_fast_forward"}]}
    ruleset.update(over)
    return ruleset


def test_the_policy_blocks_force_push_on_every_branch_with_no_bypass():
    body = nfp.policy()
    assert body["enforcement"] == "active" and body["target"] == "branch"
    assert body["conditions"]["ref_name"] == {"include": ["~ALL"], "exclude": []}
    assert body["rules"] == [{"type": "non_fast_forward"}]          # deleting a merged branch stays allowed
    assert body["bypass_actors"] == []
    assert nfp.evaluate(live()).ok


def test_every_way_to_weaken_it_fails_the_check():
    assert nfp.evaluate(None).status == "missing"
    for over, words in (
        ({"enforcement": "evaluate"}, "not active"),
        ({"conditions": {"ref_name": {"include": ["refs/heads/master"], "exclude": []}}}, "every branch"),
        ({"conditions": {"ref_name": {"include": ["~ALL"], "exclude": ["refs/heads/cursor/*"]}}}, "excludes"),
        ({"rules": [{"type": "deletion"}]}, "non_fast_forward"),
        ({"bypass_actors": [{"actor_type": "RepositoryRole", "actor_id": 5}]}, "bypass"),
    ):
        result = nfp.evaluate(live(**over))
        assert not result.ok and result.exit_code == nfp.EXIT_UNPROTECTED
        assert any(words in r for r in result.reasons), (over, result.reasons)


def test_a_bypass_list_it_cannot_see_is_never_read_as_empty():
    # GitHub returns bypass_actors only to a caller that can write rulesets (review of #961).
    hidden = live()
    del hidden["bypass_actors"]
    result = nfp.evaluate(hidden)
    assert not result.ok and result.status == "unverified" and result.exit_code == nfp.EXIT_BLOCKED


def test_without_admin_the_check_can_show_a_missing_rule_but_never_a_sound_one():
    found = nfp.evaluate_branch_rules([{"type": "non_fast_forward", "ruleset_id": 25104014}])
    assert not found.ok and found.status == "unverified" and found.exit_code == nfp.EXIT_BLOCKED
    for rules in ([{"type": "deletion"}], []):
        missing = nfp.evaluate_branch_rules(rules)
        assert not missing.ok and missing.status == "missing" and missing.exit_code == nfp.EXIT_UNPROTECTED
