"""Security alert inbox: every high or critical GitHub security alert becomes a backlog issue.

#828 item 3. In October 2026 the Security tab held 70 open alerts while Nova's
security ledger said clean: nothing routed an alert into the backlog, where agents
and the operator actually look. This tool reconciles the two, hourly
(.github/workflows/security-alert-inbox.yml):

- An open high or critical code scanning alert on the default branch, or Dependabot
  alert, with no issue gets one: labels deferred, bug, domain:security, P1 (critical)
  or P2 (high), security-alert; milestone `00 - Untriaged`; Nova Delivery board when
  NOVA_PROJECT_TOKEN is set.
- Its issue is closed again by hand while the alert is open: reopened, one comment.
- The alert is fixed: the issue closes as completed. Dismissed: as not planned,
  naming GitHub's dismissal reason only.

Why a schedule and not the alert events: GitHub delivers code_scanning_alert and
dependabot_alert to webhooks and apps only. They are not Actions workflow triggers.

Decisions are pure functions in tools/security_lib/alert_inbox.py; this file only
talks to `gh`. A failed read is an error, never "fixed": nothing closes on an unknown.
The log is public like the issues, so it prints numbers, severities and states only.

Usage:
  python tools/security_alert_inbox.py                          # reconcile (Actions)
  py -3 tools/security_alert_inbox.py --dry-run                 # read GitHub, print the plan
  py -3 tools/security_alert_inbox.py --dry-run --snapshot F    # plan from a saved snapshot
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

# Invoked as `python tools/security_alert_inbox.py`, sys.path[0] is tools/.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.backlog_github import INBOX_TITLE, repo_slug
from tools.nova_delivery_project import add_url
from tools.security_lib.alert_inbox import (
    ALERT_LABEL,
    ALERT_LABEL_COLOR,
    ALERT_LABEL_DESCRIPTION,
    CLOSE,
    CODE_SCANNING,
    CREATE,
    DEPENDABOT,
    KIND_NAMES,
    REOPEN,
    Action,
    Alert,
    Issue,
    body,
    code_scanning_alert,
    dependabot_alert,
    index_issues,
    issues_to_check,
    labels,
    parse_issue,
    plan_listed_issue,
    plan_open_alerts,
    title,
)

Runner = Callable[..., subprocess.CompletedProcess[str]]
PROJECT_TOKEN_ENV = "NOVA_PROJECT_TOKEN"
ALERT_PATHS = {CODE_SCANNING: "code-scanning/alerts", DEPENDABOT: "dependabot/alerts"}
NORMALIZE = {CODE_SCANNING: code_scanning_alert, DEPENDABOT: dependabot_alert}


class GhError(RuntimeError):
    """A `gh` call failed. The message holds gh's own error line, never a token."""


class Gh:
    """Runs `gh` for one repository; every call goes through ``runner`` so tests can see it."""

    def __init__(self, repo: str, runner: Runner = subprocess.run) -> None:
        self.repo = repo
        self.runner = runner

    def run(self, args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        extra = {"env": env} if env is not None else {}
        return self.runner(["gh", *args], capture_output=True, text=True, check=False,
                           encoding="utf-8", errors="replace", **extra)

    def ok(self, args: list[str]) -> str:
        proc = self.run(args)
        if proc.returncode != 0:
            raise GhError(_first_line(proc.stderr) or f"gh {args[0]} exited {proc.returncode}")
        return proc.stdout or ""

    def get(self, path: str) -> Any:
        return json.loads(self.ok(["api", path]) or "null")

    def get_all(self, path: str) -> list[Any]:
        pages = json.loads(self.ok(["api", "--paginate", "--slurp", path]) or "[]")
        return [item for page in pages for item in (page if isinstance(page, list) else [page])]


def _first_line(text: str | None) -> str:
    return next((line.strip() for line in (text or "").splitlines() if line.strip()), "")


class GhReader:
    """Reads alerts and inbox issues from GitHub."""

    def __init__(self, gh: Gh) -> None:
        self.gh = gh

    def default_branch(self) -> str:
        return str(self.gh.get(f"repos/{self.gh.repo}")["default_branch"])

    def open_alerts(self, kind: str, ref: str) -> list[Alert]:
        query = "state=open&per_page=100" + (f"&ref={ref}" if kind == CODE_SCANNING else "")
        rows = self.gh.get_all(f"repos/{self.gh.repo}/{ALERT_PATHS[kind]}?{query}")
        return [NORMALIZE[kind](row) for row in rows]

    def alert(self, kind: str, number: int) -> Alert | None:
        proc = self.gh.run(["api", f"repos/{self.gh.repo}/{ALERT_PATHS[kind]}/{number}"])
        if proc.returncode != 0:
            if "HTTP 404" in (proc.stderr or ""):
                return None
            raise GhError(_first_line(proc.stderr) or f"reading {KIND_NAMES[kind]} #{number} failed")
        return NORMALIZE[kind](json.loads(proc.stdout))

    def issues(self) -> list[Issue]:
        # The REST list, not the search API: search lags, and a lagging read would file twice.
        rows = self.gh.get_all(f"repos/{self.gh.repo}/issues?labels={ALERT_LABEL}&state=all&per_page=100")
        return [issue for issue in map(parse_issue, rows) if issue is not None]


class SnapshotReader:
    """Answers the same questions from a saved JSON snapshot (tests and offline dry runs).

    Shape: {"default_branch": str, "code_scanning_alerts": [...], "dependabot_alerts": [...],
    "issues": [...]}, each row as the REST API returns it.
    """

    SECTIONS = {CODE_SCANNING: "code_scanning_alerts", DEPENDABOT: "dependabot_alerts"}

    def __init__(self, data: dict) -> None:
        self.data = data

    def default_branch(self) -> str:
        return str(self.data.get("default_branch") or "master")

    def _alerts(self, kind: str) -> list[Alert]:
        return [NORMALIZE[kind](row) for row in self.data.get(self.SECTIONS[kind]) or []]

    def open_alerts(self, kind: str, ref: str) -> list[Alert]:
        return [alert for alert in self._alerts(kind) if alert.state == "open"]

    def alert(self, kind: str, number: int) -> Alert | None:
        return next((alert for alert in self._alerts(kind) if alert.number == number), None)

    def issues(self) -> list[Issue]:
        return [issue for issue in map(parse_issue, self.data.get("issues") or []) if issue is not None]


class GhWriter:
    """The only code that changes GitHub. Not constructed on a dry run."""

    def __init__(self, gh: Gh, project_token: str = "") -> None:
        self.gh = gh
        self.project_token = project_token

    def ensure_label(self) -> None:
        proc = self.gh.run(["label", "create", ALERT_LABEL, "--repo", self.gh.repo,
                            "--color", ALERT_LABEL_COLOR, "--description", ALERT_LABEL_DESCRIPTION])
        if proc.returncode != 0 and "already exists" not in (proc.stderr or ""):
            raise GhError(_first_line(proc.stderr) or f"could not create the {ALERT_LABEL} label")

    def milestone_exists(self, name: str) -> bool:
        rows = self.gh.get_all(f"repos/{self.gh.repo}/milestones?state=open&per_page=100")
        return any(row.get("title") == name for row in rows)

    def create_issue(self, alert: Alert, branch: str, milestone: str | None) -> str:
        args = ["issue", "create", "--repo", self.gh.repo, "--title", title(alert),
                "--body", body(alert, self.gh.repo, branch)]
        for name in labels(alert):
            args += ["--label", name]
        if milestone:
            args += ["--milestone", milestone]
        out = self.gh.ok(args)
        return next((line.strip() for line in reversed(out.splitlines()) if line.strip().startswith("https://")), "")

    def reopen(self, issue: Issue, comment: str) -> None:
        self.gh.ok(["issue", "reopen", str(issue.number), "--repo", self.gh.repo, "--comment", comment])

    def close(self, issue: Issue, reason: str, comment: str) -> None:
        self.gh.ok(["issue", "close", str(issue.number), "--repo", self.gh.repo,
                    "--reason", reason, "--comment", comment])

    def add_to_board(self, url: str) -> None:
        # An issue made with GITHUB_TOKEN triggers no workflow, so nova-delivery-project.yml
        # never sees it. That board is user-owned: only the project token can write it.
        if not self.project_token:
            print(f"::notice::{PROJECT_TOKEN_ENV} is not set: {url} is not on the Nova Delivery board. "
                  "Add it by hand, or set the secret (tools/nova_delivery_project.py token-help).")
            return
        env = {**os.environ, "GH_TOKEN": self.project_token}

        def with_project_token(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return self.gh.runner(cmd, env=env, **kwargs)

        if add_url(url, runner=with_project_token) != 0:
            print(f"::notice::Could not add {url} to the Nova Delivery board; the issue itself is filed.")


def plan(reader: Any, errors: list[str]) -> tuple[str, list[Action]]:
    """Read GitHub (or a snapshot) and decide. Read failures land in ``errors``."""
    branch = reader.default_branch()
    ref = f"refs/heads/{branch}"
    alerts: list[Alert] = []
    for kind in (CODE_SCANNING, DEPENDABOT):
        try:
            alerts += reader.open_alerts(kind, ref)
        except GhError as exc:
            errors.append(f"could not list open {KIND_NAMES[kind]} alerts: {exc}")
    issues = index_issues(reader.issues())
    actions = plan_open_alerts(alerts, issues, ref, now=time.time())
    for issue in issues_to_check(alerts, issues):
        try:
            alert = reader.alert(issue.kind, issue.alert_number)
        except GhError as exc:
            errors.append(f"could not read {KIND_NAMES[issue.kind]} #{issue.alert_number} for #{issue.number}: {exc}")
            continue
        actions.append(plan_listed_issue(issue, alert, branch))
    return branch, actions


def execute(actions: list[Action], writer: GhWriter, branch: str, errors: list[str]) -> None:
    milestone: str | None = None
    if any(action.verb == CREATE for action in actions):
        try:
            writer.ensure_label()
            milestone = INBOX_TITLE if writer.milestone_exists(INBOX_TITLE) else None
        except GhError as exc:
            # Without the marker label the next run could not find the issue and would file it twice.
            errors.append(f"could not prepare the {ALERT_LABEL} label or the inbox milestone: {exc}")
            actions = [action for action in actions if action.verb != CREATE]
        else:
            if milestone is None:
                errors.append(f"milestone '{INBOX_TITLE}' does not exist; filing without it. "
                              "Run: py -3 tools/backlog_triage.py sync")
    for action in actions:
        try:
            if action.verb == CREATE and action.alert is not None:
                url = writer.create_issue(action.alert, branch, milestone)
                print(f"filed {url or 'an issue'} for {action.alert.name}")
                if url:
                    writer.add_to_board(url)
            elif action.verb == REOPEN and action.issue is not None:
                writer.reopen(action.issue, action.comment)
                print(f"reopened #{action.issue.number}")
            elif action.verb == CLOSE and action.issue is not None:
                writer.close(action.issue, action.reason, action.comment)
                print(f"closed #{action.issue.number} as {action.reason}")
        except GhError as exc:
            errors.append(f"{action.verb} for {action.key} failed: {exc}")


def render(repo: str, branch: str, actions: list[Action], dry_run: bool) -> str:
    head = f"Security alert inbox for {repo} (default branch {branch})"
    lines = [head + (": dry run, nothing is written" if dry_run else "")]
    if not actions:
        lines.append("  no security-alert issues and no open alerts: nothing to do")
    lines += [f"  {action.verb:<7} {action.why}" for action in actions]
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, runner: Runner = subprocess.run) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY") or repo_slug())
    parser.add_argument("--dry-run", action="store_true", help="print the plan and write nothing")
    parser.add_argument("--snapshot", type=Path, help="read alerts and issues from this JSON file, not GitHub")
    args = parser.parse_args(argv)
    if args.snapshot and not args.dry_run:
        parser.error("--snapshot plans from a file; pass --dry-run with it")

    gh = Gh(args.repo, runner)
    reader: Any = SnapshotReader(json.loads(args.snapshot.read_text(encoding="utf-8"))) if args.snapshot else GhReader(gh)
    errors: list[str] = []
    try:
        branch, actions = plan(reader, errors)
    except GhError as exc:
        print(f"::error::Security alert inbox could not read GitHub: {exc}")
        return 1
    print(render(args.repo, branch, actions, args.dry_run))
    if not args.dry_run:
        execute(actions, GhWriter(gh, os.environ.get(PROJECT_TOKEN_ENV, "")), branch, errors)
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
