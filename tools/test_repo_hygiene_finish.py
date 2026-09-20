"""Cleanup must report failures and verify its postconditions."""
from argparse import Namespace
import subprocess
from unittest.mock import Mock

import pytest

from tools import repo_hygiene as hygiene


def setup_run(monkeypatch, snapshots, fetch_code=0):
    run = Mock(return_value=subprocess.CompletedProcess([], fetch_code, '', ''))
    monkeypatch.setattr(hygiene.subprocess, 'run', run)
    monkeypatch.setattr(hygiene, 'gather', Mock(side_effect=snapshots))
    return run


def fix(dry=False):
    return hygiene.cmd_fix(Namespace(dry_run=dry, max_age_hours=24))


def finding(kind='merged_local_branch', name='done', fixable=True):
    return hygiene.Finding(kind, name, 'test', fixable)


def test_failed_fetch_stops_before_inspection_or_deletion(monkeypatch):
    setup_run(monkeypatch, [], fetch_code=1)
    assert fix() == 2
    hygiene.gather.assert_not_called()


def test_failed_delete_is_not_success_even_when_printed(monkeypatch):
    monkeypatch.setattr(hygiene, 'contained_tip', lambda *a, **kw: 'abc')
    monkeypatch.setattr(hygiene, '_gh_prs', lambda: [{'head': 'done', 'state': 'MERGED'}])
    monkeypatch.setattr(hygiene, '_worktrees', lambda: [])
    run = setup_run(monkeypatch, [([finding()], True)])
    run.side_effect = [subprocess.CompletedProcess([], 0, '', ''),
                       subprocess.CompletedProcess([], 1, '', 'locked worktree')]
    assert fix() == 2
    assert run.call_count == 2


def test_worktree_then_exposed_branch_are_both_cleaned(monkeypatch):
    setup_run(monkeypatch, [([finding('worktree_stale')], True),
                            ([finding()], True), ([], True)])
    action = Mock(return_value=(True, 'ok'))
    monkeypatch.setattr(hygiene, '_apply', action)
    assert fix() == 0
    assert action.call_count == 2
    assert hygiene.gather.call_count == 3


def test_successful_command_with_remaining_finding_is_not_clean(monkeypatch):
    setup_run(monkeypatch, [([finding()], True)] * 3)
    monkeypatch.setattr(hygiene, '_apply', Mock(return_value=(True, 'ok')))
    assert fix() == 1


@pytest.mark.parametrize('gh_ok,expected', [(True, 0), (False, 2)])
def test_empty_scan_requires_available_github(monkeypatch, gh_ok, expected):
    setup_run(monkeypatch, [([], gh_ok)])
    assert fix() == expected


def test_report_only_findings_are_preserved(monkeypatch):
    setup_run(monkeypatch, [([finding('stash_present', fixable=False)], True)])
    assert fix() == 1


def test_dry_run_does_not_fetch_or_delete(monkeypatch):
    run = setup_run(monkeypatch, [([finding()], True)])
    assert fix(dry=True) == 1
    run.assert_not_called()


def test_inspection_error_returns_failure(monkeypatch):
    setup_run(monkeypatch, [OSError('unavailable')])
    assert fix() == 2


def test_status_does_not_claim_clean_when_github_is_down(monkeypatch, capsys):
    setup_run(monkeypatch, [([], False)])
    assert hygiene.cmd_status(Namespace(max_age_hours=24, json=False)) == 2
    assert 'OK' not in capsys.readouterr().out


def test_status_inspection_failure_has_distinct_exit_code(monkeypatch):
    setup_run(monkeypatch, [OSError('git unavailable')])
    assert hygiene.cmd_status(Namespace(max_age_hours=24, json=False)) == 2


@pytest.mark.parametrize('kind', ['merged_local_branch', 'worktree_stale'])
def test_apply_rechecks_tip_and_preserves_new_work(monkeypatch, kind):
    monkeypatch.setattr(hygiene, 'contained_tip', lambda *a, **kw: None)
    run = Mock()
    monkeypatch.setattr(hygiene.subprocess, 'run', run)
    ok, reason = hygiene._apply(finding(kind), False)
    assert not ok and 'not contained' in reason
    run.assert_not_called()


def test_local_delete_uses_expected_tip(monkeypatch):
    monkeypatch.setattr(hygiene, 'contained_tip', lambda *a, **kw: 'verified-sha')
    monkeypatch.setattr(hygiene, '_gh_prs', lambda: [{'head': 'done', 'state': 'MERGED'}])
    monkeypatch.setattr(hygiene, '_worktrees', lambda: [])
    run = Mock(return_value=subprocess.CompletedProcess([], 0, '', ''))
    monkeypatch.setattr(hygiene.subprocess, 'run', run)
    assert hygiene._apply(finding(), False)[0]
    assert run.call_args.args[0] == ['git', 'update-ref', '-d', 'refs/heads/done', 'verified-sha']


@pytest.mark.parametrize('prs', [None, [], [{'head': 'done', 'state': 'OPEN'}]])
def test_local_delete_requires_fresh_closed_pr_evidence(monkeypatch, prs):
    monkeypatch.setattr(hygiene, 'contained_tip', lambda *a, **kw: 'verified-sha')
    monkeypatch.setattr(hygiene, '_gh_prs', lambda: prs)
    run = Mock()
    monkeypatch.setattr(hygiene.subprocess, 'run', run)
    assert not hygiene._apply(finding(), False)[0]
    run.assert_not_called()
