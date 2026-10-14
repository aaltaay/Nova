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


def test_without_admin_the_check_reads_the_rules_a_new_branch_gets():
    assert nfp.evaluate_branch_rules([{"type": "non_fast_forward", "ruleset_id": 25104014}]).ok
    assert not nfp.evaluate_branch_rules([{"type": "deletion"}]).ok
    assert not nfp.evaluate_branch_rules([]).ok
