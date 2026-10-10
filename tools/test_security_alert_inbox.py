"""Contract tests for the security alert inbox (#828 item 3).

Run from repo root:
    py -3 -m pytest tools/test_security_alert_inbox.py -q

Alert fixtures follow GitHub's REST alert shapes (code-scanning/alerts and
dependabot/alerts, checked against the live API on 2026-10-09). Every detail a
public issue must never carry -- rule, file, line, package, advisory -- is set to
a distinctive value so the leak tests can look for it.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.security_alert_inbox import Gh, GhReader, GhWriter, SnapshotReader, execute, main, plan  # noqa: E402
from tools.security_lib.alert_inbox import (  # noqa: E402
    CLOSE,
    CODE_SCANNING,
    CREATE,
    DEPENDABOT,
    IGNORE,
    KEEP,
    REOPEN,
    Issue,
    body,
    code_scanning_alert,
    dependabot_alert,
    index_issues,
    issues_to_check,
    labels,
    marker,
    parse_issue,
    plan_listed_issue,
    plan_open_alerts,
    REOPEN_GRACE_SEC,
    title,
)

REPO = "aaltaay/Nova"
REF = "refs/heads/master"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "security-alert-inbox.yml"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy.yml"

SECRETS = (
    "py/sql-injection-secret-rule", "SQL query built from user-controlled sources",
    "backend/secret_module/handler.py", "4242", "leftpad-secret-pkg",
    "frontend/package-lock.json", "GHSA-xxxx-yyyy-zzzz", "CVE-2099-0001",
    "Prototype pollution in leftpad-secret-pkg", "we accept this risk because of reasons",
)


def cs_raw(number=12, *, state="open", level="high", ref=REF, reason=None, comment=None):
    return {
        "number": number, "state": state, "dismissed_reason": reason, "dismissed_comment": comment,
        "fixed_at": "2026-10-10T02:35:35Z" if state == "fixed" else None,
        "html_url": f"https://github.com/{REPO}/security/code-scanning/{number}",
        "rule": {"id": "py/sql-injection-secret-rule", "severity": "error",
                 "security_severity_level": level, "name": "py/sql-injection-secret-rule",
                 "description": "SQL query built from user-controlled sources", "tags": ["security"]},
        "tool": {"name": "CodeQL", "version": "2.23.0"},
        "most_recent_instance": {"ref": ref, "state": state, "commit_sha": "a" * 40,
                                 "location": {"path": "backend/secret_module/handler.py",
                                              "start_line": 4242, "end_line": 4242}},
    }


def dep_raw(number=7, *, state="open", severity="critical", reason=None, comment=None):
    return {
        "number": number, "state": state, "dismissed_reason": reason, "dismissed_comment": comment,
        "auto_dismissed_at": "2026-10-09T00:00:00Z" if state == "auto_dismissed" else None,
        "html_url": f"https://github.com/{REPO}/security/dependabot/{number}",
        "dependency": {"package": {"ecosystem": "npm", "name": "leftpad-secret-pkg"},
                       "manifest_path": "frontend/package-lock.json", "scope": "development"},
        "security_advisory": {"ghsa_id": "GHSA-xxxx-yyyy-zzzz", "cve_id": "CVE-2099-0001",
                              "summary": "Prototype pollution in leftpad-secret-pkg", "severity": severity},
        "security_vulnerability": {"package": {"name": "leftpad-secret-pkg"}, "severity": severity},
    }


def issue_raw(number, key, *, state="open"):
    return {"number": number, "state": state, "html_url": f"https://github.com/{REPO}/issues/{number}",
            "body": f"text\n\n{marker(key)}", "labels": [{"name": "security-alert"}]}


def verbs(actions):
    return [(action.verb, action.key) for action in actions]


# ---------------------------------------------------------------- normalizing


def test_code_scanning_alert_reads_number_state_severity_and_ref_only():
    alert = code_scanning_alert(cs_raw(state="dismissed", reason="won't fix", comment="private words"))
    assert (alert.kind, alert.number, alert.state, alert.severity, alert.ref) == (
        CODE_SCANNING, 12, "dismissed", "high", REF)
    assert alert.dismissed_reason == "won't fix"
    assert "private words" not in repr(alert)


def test_dependabot_auto_dismissed_folds_into_dismissed():
    alert = dependabot_alert(dep_raw(state="auto_dismissed"))
    assert (alert.kind, alert.state, alert.auto_dismissed, alert.severity) == (DEPENDABOT, "dismissed", True, "critical")


def test_unknown_dismissal_reason_is_dropped():
    assert dependabot_alert(dep_raw(state="dismissed", reason="free text?")).dismissed_reason == ""


# ---------------------------------------------------------------- filing


@pytest.mark.parametrize("level,expected", [("critical", "P1"), ("high", "P2")])
def test_open_high_or_critical_alert_without_issue_is_filed(level, expected):
    alert = code_scanning_alert(cs_raw(level=level))
    [action] = plan_open_alerts([alert], {}, REF)
    assert action.verb == CREATE
    assert labels(alert) == ["deferred", "bug", "domain:security", expected, "security-alert"]


@pytest.mark.parametrize("level", ["medium", "low", None])
def test_medium_low_and_unrated_code_scanning_alerts_are_ignored(level):
    [action] = plan_open_alerts([code_scanning_alert(cs_raw(level=level))], {}, REF)
    assert action.verb == IGNORE
    assert "only high and critical" in action.why


@pytest.mark.parametrize("severity", ["medium", "low"])
def test_medium_and_low_dependabot_alerts_are_ignored(severity):
    [action] = plan_open_alerts([dependabot_alert(dep_raw(severity=severity))], {}, REF)
    assert action.verb == IGNORE


def test_pull_request_ref_alert_is_ignored():
    [action] = plan_open_alerts([code_scanning_alert(cs_raw(ref="refs/pull/7/merge"))], {}, REF)
    assert action.verb == IGNORE
    assert "refs/pull/7/merge" in action.why


def test_marker_dedupe_open_keeps_closed_reopens_none_creates():
    alerts = [code_scanning_alert(cs_raw(1)), code_scanning_alert(cs_raw(2)), dependabot_alert(dep_raw(3))]
    issues = index_issues([parse_issue(issue_raw(900, "codeql/1")),
                           parse_issue(issue_raw(901, "codeql/2", state="closed"))])
    actions = plan_open_alerts(alerts, issues, REF)
    assert verbs(actions) == [(KEEP, "codeql/1"), (REOPEN, "codeql/2"), (CREATE, "dependabot/3")]
    assert actions[1].issue.number == 901 and "still open on GitHub" in actions[1].comment


def test_an_issue_a_fix_pr_just_closed_stays_closed_inside_the_grace_window():
    # `Closes #N` closes the issue on merge, minutes before GitHub marks the alert fixed.
    closed = issue_raw(901, "codeql/2", state="closed")
    closed["closed_at"] = "2026-10-10T02:00:00Z"
    issues = index_issues([parse_issue(closed)])
    closed_ts = parse_issue(closed).closed_at
    alerts = [code_scanning_alert(cs_raw(2))]
    [held] = plan_open_alerts(alerts, issues, REF, now=closed_ts + 600)
    assert held.verb == KEEP and "#901 closed 0.2 h ago" in held.why
    [reopened] = plan_open_alerts(alerts, issues, REF, now=closed_ts + REOPEN_GRACE_SEC + 1)
    assert reopened.verb == REOPEN
    # No close time known (or no clock given): reopen, as before.
    assert plan_open_alerts(alerts, index_issues([parse_issue(issue_raw(901, "codeql/2", state="closed"))]),
                            REF, now=closed_ts + 600)[0].verb == REOPEN


def test_dependabot_marker_never_matches_a_code_scanning_alert_with_the_same_number():
    issues = index_issues([parse_issue(issue_raw(900, "dependabot/5"))])
    assert verbs(plan_open_alerts([code_scanning_alert(cs_raw(5))], issues, REF)) == [(CREATE, "codeql/5")]


def test_open_issue_wins_over_a_closed_duplicate():
    issues = index_issues([Issue(800, "closed", "codeql/1"), Issue(950, "open", "codeql/1")])
    assert issues["codeql/1"].number == 950


def test_issue_without_marker_or_a_pull_request_is_not_an_inbox_issue():
    assert parse_issue({"number": 1, "state": "open", "body": "no marker"}) is None
    assert parse_issue({**issue_raw(2, "codeql/9"), "pull_request": {"url": "x"}}) is None
    assert parse_issue(issue_raw(3, "dependabot/9")).key == "dependabot/9"


# ---------------------------------------------------------------- closing


def test_fixed_alert_closes_its_issue_as_completed():
    action = plan_listed_issue(Issue(900, "open", "codeql/12"), code_scanning_alert(cs_raw(state="fixed")), "master")
    assert (action.verb, action.reason) == (CLOSE, "completed")
    assert "fixed on `master`" in action.comment


@pytest.mark.parametrize("raw,reason", [
    (cs_raw(state="dismissed", reason="false positive", comment="we accept this risk because of reasons"),
     "false positive"),
    (dep_raw(state="dismissed", reason="tolerable_risk", comment="we accept this risk because of reasons"),
     "tolerable_risk"),
])
def test_dismissed_alert_closes_as_not_planned_naming_the_reason_only(raw, reason):
    alert = (code_scanning_alert if "rule" in raw else dependabot_alert)(raw)
    action = plan_listed_issue(Issue(900, "open", alert.key), alert, "master")
    assert (action.verb, action.reason) == (CLOSE, "not planned")
    assert f"reason: {reason}" in action.comment
    assert "we accept this risk" not in action.comment


def test_auto_dismissed_dependabot_alert_closes_as_not_planned():
    action = plan_listed_issue(Issue(900, "open", "dependabot/7"), dependabot_alert(dep_raw(state="auto_dismissed")), "m")
    assert (action.verb, action.reason) == (CLOSE, "not planned")
    assert "auto-triage rule" in action.comment


def test_missing_or_still_open_alert_keeps_the_issue_open():
    issue = Issue(900, "open", "codeql/12")
    assert plan_listed_issue(issue, None, "master").verb == KEEP
    assert plan_listed_issue(issue, code_scanning_alert(cs_raw()), "master").verb == KEEP


def test_only_open_issues_missing_from_the_open_list_are_checked():
    issues = index_issues([Issue(900, "open", "codeql/1"), Issue(901, "open", "codeql/2"),
                           Issue(902, "closed", "codeql/3")])
    listed = [code_scanning_alert(cs_raw(1, level="medium"))]
    assert [issue.number for issue in issues_to_check(listed, issues)] == [901]


# ---------------------------------------------------------------- what a public issue may say


@pytest.mark.parametrize("alert", [code_scanning_alert(cs_raw(level="critical")), dependabot_alert(dep_raw())])
def test_title_and_body_never_carry_alert_details(alert):
    text = title(alert) + "\n" + body(alert, REPO, "master")
    for secret in SECRETS:
        assert secret not in text, secret
    assert marker(alert.key) in text
    assert alert.html_url in text
    assert "Do not paste the alert's details here: this repository is public." in text
    assert "This issue closes itself when the alert is fixed or dismissed." in text
    assert "written reason" in text


def test_titles_name_kind_number_and_severity():
    assert title(code_scanning_alert(cs_raw(12))) == "Security alert needs triage: code scanning #12 (high)"
    assert title(dependabot_alert(dep_raw(7))) == "Security alert needs triage: Dependabot #7 (critical)"


def test_unexpected_html_url_is_replaced_by_a_built_link():
    raw = {**dep_raw(7), "html_url": "https://example.com/leftpad-secret-pkg"}
    text = body(dependabot_alert(raw), REPO, "master")
    assert "leftpad-secret-pkg" not in text
    assert f"https://github.com/{REPO}/security/dependabot/7" in text


# ---------------------------------------------------------------- the gh layer


class FakeGh:
    """Answers `gh` like GitHub would and records every call."""

    def __init__(self, *, cs=(), dep=(), issues=(), fail=(), milestones=("00 - Untriaged",)):
        self.cs, self.dep, self.issue_rows = list(cs), list(dep), list(issues)
        self.fail, self.milestones, self.calls = set(fail), milestones, []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        args = cmd[1:]

        def done(out="", code=0, err=""):
            return subprocess.CompletedProcess(cmd, code, out, err)

        if any(word in " ".join(args) for word in self.fail):
            return done(code=1, err="gh: Resource not accessible by integration (HTTP 403)")
        if args[0] != "api":
            return done(out=f"https://github.com/{REPO}/issues/990\n" if args[:2] == ["issue", "create"] else "")
        path = args[-1]
        if path == f"repos/{REPO}":
            return done(json.dumps({"default_branch": "master"}))
        for kind, rows in (("code-scanning", self.cs), ("dependabot", self.dep)):
            prefix = f"repos/{REPO}/{kind}/alerts"
            if path.startswith(prefix + "?"):
                return done(json.dumps([[row for row in rows if row["state"] == "open"]]))
            if path.startswith(prefix + "/"):
                match = [row for row in rows if row["number"] == int(path.rsplit("/", 1)[1])]
                return done(json.dumps(match[0])) if match else done(code=1, err="gh: Not Found (HTTP 404)")
        if path.startswith(f"repos/{REPO}/issues?"):
            return done(json.dumps([self.issue_rows]))
        if path.startswith(f"repos/{REPO}/milestones?"):
            return done(json.dumps([[{"title": name} for name in self.milestones]]))
        raise AssertionError(f"unexpected gh call: {cmd}")

    def writes(self):
        return [cmd for cmd, _ in self.calls if cmd[1] != "api"]


def scenario():
    return FakeGh(
        cs=[cs_raw(12, level="high"), cs_raw(13, level="medium"), cs_raw(14, state="fixed")],
        dep=[dep_raw(7, severity="critical"), dep_raw(8, state="dismissed", reason="not_used")],
        issues=[issue_raw(900, "codeql/14"), issue_raw(901, "dependabot/8")],
    )


def test_dry_run_prints_the_plan_and_writes_nothing(capsys, monkeypatch):
    monkeypatch.setenv("NOVA_PROJECT_TOKEN", "x")
    fake = scenario()
    assert main(["--repo", REPO, "--dry-run"], runner=fake) == 0
    out = capsys.readouterr().out
    assert fake.writes() == []
    assert all(cmd[:2] == ["gh", "api"] and "-X" not in cmd and "--method" not in cmd for cmd, _ in fake.calls)
    assert "dry run, nothing is written" in out
    for line in ("create  code scanning #12", "ignore  code scanning #13", "close   code scanning #14",
                 "create  Dependabot #7", "close   Dependabot #8"):
        assert line in out
    for secret in SECRETS:
        assert secret not in out


def test_snapshot_dry_run_reads_no_github_at_all(tmp_path, capsys):
    snapshot = tmp_path / "snap.json"
    snapshot.write_text(json.dumps({"default_branch": "master", "code_scanning_alerts": [cs_raw(12)],
                                    "dependabot_alerts": [], "issues": []}), encoding="utf-8")
    fake = FakeGh()
    assert main(["--repo", REPO, "--dry-run", "--snapshot", str(snapshot)], runner=fake) == 0
    assert fake.calls == []
    assert "create  code scanning #12" in capsys.readouterr().out


def test_snapshot_without_dry_run_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        main(["--snapshot", str(tmp_path / "x.json")], runner=FakeGh())


def test_run_files_reopens_and_closes_with_labels_milestone_and_reasons(monkeypatch, capsys):
    monkeypatch.setenv("NOVA_PROJECT_TOKEN", "project-token-value")
    fake = scenario()
    fake.issue_rows.append(issue_raw(902, "codeql/12", state="closed"))
    assert main(["--repo", REPO], runner=fake) == 0
    writes = fake.writes()
    assert writes[0][:4] == ["gh", "label", "create", "security-alert"]
    reopen = next(cmd for cmd in writes if cmd[1:3] == ["issue", "reopen"])
    assert reopen[3] == "902" and "--comment" in reopen
    create = next(cmd for cmd in writes if cmd[1:3] == ["issue", "create"])
    assert create[create.index("--title") + 1] == "Security alert needs triage: Dependabot #7 (critical)"
    assert [create[i + 1] for i, word in enumerate(create) if word == "--label"] == [
        "deferred", "bug", "domain:security", "P1", "security-alert"]
    assert create[create.index("--milestone") + 1] == "00 - Untriaged"
    closes = {cmd[3]: cmd[cmd.index("--reason") + 1] for cmd in writes if cmd[1:3] == ["issue", "close"]}
    assert closes == {"900": "completed", "901": "not planned"}
    board = [(cmd, kw) for cmd, kw in fake.calls if cmd[1:3] == ["project", "item-add"]]
    assert board and board[0][1]["env"]["GH_TOKEN"] == "project-token-value"
    assert "project-token-value" not in capsys.readouterr().out


def test_missing_project_token_is_a_notice_not_a_failure(monkeypatch, capsys):
    monkeypatch.delenv("NOVA_PROJECT_TOKEN", raising=False)
    fake = FakeGh(dep=[dep_raw(7)])
    assert main(["--repo", REPO], runner=fake) == 0
    assert "::notice::NOVA_PROJECT_TOKEN is not set" in capsys.readouterr().out
    assert not any(cmd[1] == "project" for cmd, _ in fake.calls)


def test_missing_inbox_milestone_still_files_but_fails_loud(monkeypatch, capsys):
    monkeypatch.delenv("NOVA_PROJECT_TOKEN", raising=False)
    fake = FakeGh(dep=[dep_raw(7)], milestones=())
    assert main(["--repo", REPO], runner=fake) == 1
    create = next(cmd for cmd in fake.writes() if cmd[1:3] == ["issue", "create"])
    assert "--milestone" not in create
    assert "::error::milestone '00 - Untriaged' does not exist" in capsys.readouterr().out


def test_a_label_failure_files_nothing_rather_than_a_duplicate_later(monkeypatch):
    monkeypatch.delenv("NOVA_PROJECT_TOKEN", raising=False)
    fake = FakeGh(dep=[dep_raw(7)], fail=("label create",))
    assert main(["--repo", REPO], runner=fake) == 1
    assert not any(cmd[1:3] == ["issue", "create"] for cmd in fake.writes())


def test_a_failed_alert_read_never_closes_an_issue(capsys):
    fake = FakeGh(cs=[cs_raw(14, state="fixed")], issues=[issue_raw(900, "codeql/14")],
                  fail=("code-scanning/alerts",))
    assert main(["--repo", REPO], runner=fake) == 1
    assert fake.writes() == []
    assert "::error::could not read code scanning #14 for #900" in capsys.readouterr().out


def test_an_unreadable_issue_list_stops_before_any_write():
    fake = FakeGh(dep=[dep_raw(7)], fail=("issues?",))
    assert main(["--repo", REPO], runner=fake) == 1
    assert fake.writes() == []


def test_open_code_scanning_list_asks_for_the_default_branch():
    fake = scenario()
    GhReader(Gh(REPO, fake)).open_alerts(CODE_SCANNING, REF)
    assert fake.calls[-1][0][-1].endswith(f"state=open&per_page=100&ref={REF}")
    assert fake.calls[-1][0][2:4] == ["--paginate", "--slurp"]


def test_snapshot_and_live_reader_reach_the_same_plan():
    fake = scenario()
    snapshot = SnapshotReader({"default_branch": "master", "code_scanning_alerts": copy.deepcopy(fake.cs),
                               "dependabot_alerts": copy.deepcopy(fake.dep), "issues": fake.issue_rows})
    assert verbs(plan(GhReader(Gh(REPO, fake)), [])[1]) == verbs(plan(snapshot, [])[1])


def test_execute_skips_keep_and_ignore(monkeypatch):
    monkeypatch.delenv("NOVA_PROJECT_TOKEN", raising=False)
    fake = FakeGh(cs=[cs_raw(1, level="low")], issues=[issue_raw(900, "codeql/1")])
    branch, actions = plan(GhReader(Gh(REPO, fake)), [])
    execute(actions, GhWriter(Gh(REPO, fake)), branch, [])
    assert fake.writes() == []


# ---------------------------------------------------------------- the workflow


def test_workflow_polls_with_least_privilege_and_never_overlaps():
    wf = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    # code_scanning_alert / dependabot_alert are webhook events, not workflow triggers.
    assert set(wf["on"]) == {"schedule", "workflow_dispatch"}
    assert wf["on"]["schedule"][0]["cron"]
    assert wf["permissions"] == {"contents": "read", "issues": "write",
                                 "security-events": "read", "vulnerability-alerts": "read"}
    assert wf["concurrency"]["cancel-in-progress"] == "false"
    [job] = wf["jobs"].values()
    assert job["timeout-minutes"]
    step = job["steps"][-1]
    assert step["run"] == "python tools/security_alert_inbox.py"
    assert step["env"]["NOVA_PROJECT_TOKEN"] == "${{ secrets.NOVA_PROJECT_TOKEN }}"


def test_ci_runs_these_tests():
    assert "tools/test_security_alert_inbox.py" in DEPLOY.read_text(encoding="utf-8")
