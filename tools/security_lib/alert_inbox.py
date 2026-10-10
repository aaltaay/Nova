"""Security alert inbox decisions: which GitHub security alert gets, keeps or closes an issue.

Pure functions only (AGENTS.md invariant 2): they read alert and issue records and
return a plan. ``tools/security_alert_inbox.py`` does the GitHub I/O around them.

The repository is public. Everything built here -- titles, bodies, comments and the
one-line reasons the tool prints into a public Actions log -- carries an alert's kind,
number, severity, state and dismissal reason only. Never the rule, file, line,
package or advisory text: SECURITY.md says never disclose a vulnerability in public.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

CODE_SCANNING = "codeql"
DEPENDABOT = "dependabot"
KIND_NAMES = {CODE_SCANNING: "code scanning", DEPENDABOT: "Dependabot"}

# Only these become issues. Critical is P1 on purpose: `backlog_triage.py check`
# fails while a P1 sits untriaged, so a critical alert cannot be overlooked.
PRIORITY = {"critical": "P1", "high": "P2"}
BASE_LABELS = ("deferred", "bug", "domain:security")
ALERT_LABEL = "security-alert"
ALERT_LABEL_COLOR = "B60205"
ALERT_LABEL_DESCRIPTION = "Filed from a GitHub security alert; closes itself when the alert is fixed or dismissed"

# GitHub's dismissal reasons (REST + webhook schemas). Anything else is reported as
# "no reason given"; the free-text dismissal comment is never read.
DISMISSED_REASONS = {
    CODE_SCANNING: ("false positive", "won't fix", "used in tests", "mitigated"),
    DEPENDABOT: ("fix_started", "inaccurate", "no_bandwidth", "not_used", "tolerable_risk"),
}

MARKER_RE = re.compile(r"<!-- nova-security-alert: (codeql|dependabot)/(\d+) -->")
LINK_RE = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/security/(code-scanning|dependabot)/(\d+)")
LINK_PATH = {CODE_SCANNING: "code-scanning", DEPENDABOT: "dependabot"}

# A fix PR that says `Closes #N` closes the issue on merge, minutes before CodeQL on
# master or the Dependabot graph marks the alert fixed. An issue closed less than this
# long ago stays closed while its alert is still listed open; past it, it reopens.
REOPEN_GRACE_SEC = 12 * 3600

CREATE, REOPEN, CLOSE, KEEP, IGNORE = "create", "reopen", "close", "keep", "ignore"
COMPLETED, NOT_PLANNED = "completed", "not planned"


@dataclass(frozen=True)
class Alert:
    kind: str
    number: int
    state: str  # open | fixed | dismissed (Dependabot's auto_dismissed folds into dismissed)
    severity: str  # critical | high | medium | low | "" when GitHub gives no security rating
    html_url: str = ""
    dismissed_reason: str = ""  # one of DISMISSED_REASONS, else ""
    ref: str = ""  # code scanning: the ref of the alert's most recent instance
    auto_dismissed: bool = False

    @property
    def key(self) -> str:
        return f"{self.kind}/{self.number}"

    @property
    def name(self) -> str:
        return f"{KIND_NAMES[self.kind]} #{self.number}"


@dataclass(frozen=True)
class Issue:
    number: int
    state: str  # open | closed
    key: str  # the marker's "<kind>/<number>"
    url: str = ""
    closed_at: float | None = None  # epoch seconds; None when open or unknown

    @property
    def kind(self) -> str:
        return self.key.split("/", 1)[0]

    @property
    def alert_number(self) -> int:
        return int(self.key.split("/", 1)[1])


@dataclass(frozen=True)
class Action:
    verb: str  # create | reopen | close | keep | ignore
    key: str
    why: str  # one line, safe for a public log
    alert: Alert | None = None
    issue: Issue | None = None
    reason: str = ""  # close only: completed | not planned
    comment: str = ""  # reopen / close only


def _known_reason(kind: str, raw: object) -> str:
    text = str(raw or "")
    return text if text in DISMISSED_REASONS[kind] else ""


def code_scanning_alert(raw: dict) -> Alert:
    """An alert from GET /repos/{repo}/code-scanning/alerts[/{n}]."""
    rule = raw.get("rule") or {}
    instance = raw.get("most_recent_instance") or {}
    return Alert(
        kind=CODE_SCANNING,
        number=int(raw["number"]),
        state=str(raw.get("state") or ""),
        severity=str(rule.get("security_severity_level") or "").lower(),
        html_url=str(raw.get("html_url") or ""),
        dismissed_reason=_known_reason(CODE_SCANNING, raw.get("dismissed_reason")),
        ref=str(instance.get("ref") or ""),
    )


def dependabot_alert(raw: dict) -> Alert:
    """An alert from GET /repos/{repo}/dependabot/alerts[/{n}]."""
    advisory = raw.get("security_advisory") or {}
    vulnerability = raw.get("security_vulnerability") or {}
    state = str(raw.get("state") or "")
    auto = state == "auto_dismissed"
    return Alert(
        kind=DEPENDABOT,
        number=int(raw["number"]),
        state="dismissed" if auto else state,
        severity=str(advisory.get("severity") or vulnerability.get("severity") or "").lower(),
        html_url=str(raw.get("html_url") or ""),
        dismissed_reason=_known_reason(DEPENDABOT, raw.get("dismissed_reason")),
        auto_dismissed=auto,
    )


def marker(key: str) -> str:
    return f"<!-- nova-security-alert: {key} -->"


def _epoch(raw: object) -> float | None:
    """GitHub's ISO time ("2026-10-10T02:32:48Z") as epoch seconds, or None."""
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp() if raw else None
    except ValueError:
        return None


def parse_issue(raw: dict) -> Issue | None:
    """An issue from the REST issues list, or None when it carries no inbox marker."""
    if raw.get("pull_request"):
        return None
    match = MARKER_RE.search(str(raw.get("body") or ""))
    if not match:
        return None
    return Issue(
        number=int(raw["number"]),
        state=str(raw.get("state") or ""),
        key=f"{match.group(1)}/{match.group(2)}",
        url=str(raw.get("html_url") or ""),
        closed_at=_epoch(raw.get("closed_at")),
    )


def index_issues(issues: Iterable[Issue]) -> dict[str, Issue]:
    """One issue per alert: an open one wins over a closed one, then the oldest."""
    best: dict[str, Issue] = {}
    for issue in sorted(issues, key=lambda item: (item.state != "open", item.number)):
        best.setdefault(issue.key, issue)
    return best


def priority(alert: Alert) -> str:
    return PRIORITY[alert.severity]


def labels(alert: Alert) -> list[str]:
    return [*BASE_LABELS, priority(alert), ALERT_LABEL]


def title(alert: Alert) -> str:
    return f"Security alert needs triage: {alert.name} ({alert.severity})"


def alert_link(alert: Alert, repo: str) -> str:
    """GitHub's own link when it has the expected shape, else one built from the number."""
    match = LINK_RE.fullmatch(alert.html_url.rstrip("/"))
    if match and match.group(1) == LINK_PATH[alert.kind] and int(match.group(2)) == alert.number:
        return alert.html_url.rstrip("/")
    return f"https://github.com/{repo}/security/{LINK_PATH[alert.kind]}/{alert.number}"


def body(alert: Alert, repo: str, branch: str) -> str:
    where = f"on `{branch}`" if alert.kind == CODE_SCANNING else "in Nova's dependencies"
    return "\n".join([
        f"GitHub's Security tab has an open **{alert.severity}** {KIND_NAMES[alert.kind]} alert {where}:",
        alert_link(alert, repo),
        "",
        "The link opens only for people with access to this repository's security alerts.",
        "",
        "**What to do**",
        "",
        "- Fix it in a pull request. This issue closes itself as completed once GitHub marks the alert fixed.",
        "- Or, if it does not apply to Nova, dismiss the alert on GitHub with a written reason, "
        "the way PR #829 handled 70 alerts. This issue then closes itself as not planned.",
        "",
        "**Do not paste the alert's details here: this repository is public.** Keep them on the alert "
        "itself, or in a private security advisory.",
        "",
        "This issue closes itself when the alert is fixed or dismissed. Closed while the alert is "
        "still open 12 hours later, it opens again.",
        "",
        marker(alert.key),
    ])


REOPEN_COMMENT = (
    "The alert is still open on GitHub, so this issue is open again. Fix it in a pull request, "
    "or dismiss the alert on GitHub with a written reason."
)


def skip_reason(alert: Alert, default_ref: str) -> str:
    """Why an alert gets no issue, or "" when it should have one."""
    if alert.state != "open":
        return f"is {alert.state or 'in an unknown state'}"
    if alert.kind == CODE_SCANNING and alert.ref and alert.ref != default_ref:
        # A pull request's alert goes away when that pull request fixes it.
        return f"is on {alert.ref}, not {default_ref}"
    if alert.severity not in PRIORITY:
        rating = f"rated {alert.severity}" if alert.severity else "has no security severity"
        return f"is {rating}; only high and critical alerts become issues"
    return ""


def plan_open_alerts(
    alerts: Iterable[Alert], issues: dict[str, Issue], default_ref: str, now: float | None = None,
) -> list[Action]:
    """File, keep or reopen an issue for every open alert GitHub listed.

    ``now`` (epoch seconds) holds back a reopen inside ``REOPEN_GRACE_SEC`` of the close."""
    actions: list[Action] = []
    for alert in sorted(alerts, key=lambda item: (item.kind, item.number)):
        why_not = skip_reason(alert, default_ref)
        issue = issues.get(alert.key)
        if why_not:
            actions.append(Action(IGNORE, alert.key, f"{alert.name} {why_not}", alert=alert, issue=issue))
        elif issue is None:
            why = f"{alert.name} is open and {alert.severity}: file an issue ({priority(alert)})"
            actions.append(Action(CREATE, alert.key, why, alert=alert))
        elif issue.state == "open":
            actions.append(Action(KEEP, alert.key, f"{alert.name} is tracked in #{issue.number}", alert=alert, issue=issue))
        elif now is not None and issue.closed_at is not None and now - issue.closed_at < REOPEN_GRACE_SEC:
            hours = (now - issue.closed_at) / 3600
            why = (f"{alert.name} is still listed open; #{issue.number} closed {hours:.1f} h ago, "
                   f"waiting up to {REOPEN_GRACE_SEC // 3600} h for GitHub to mark it fixed")
            actions.append(Action(KEEP, alert.key, why, alert=alert, issue=issue))
        else:
            why = f"{alert.name} is open again: reopen #{issue.number}"
            actions.append(Action(REOPEN, alert.key, why, alert=alert, issue=issue, comment=REOPEN_COMMENT))
    return actions


def issues_to_check(alerts: Iterable[Alert], issues: dict[str, Issue]) -> list[Issue]:
    """Open issues whose alert GitHub did not list as open: each needs its alert read."""
    listed_open = {alert.key for alert in alerts if alert.state == "open"}
    return sorted(
        (issue for issue in issues.values() if issue.state == "open" and issue.key not in listed_open),
        key=lambda issue: issue.number,
    )


def close_comment(alert: Alert, branch: str) -> str:
    if alert.state == "fixed":
        where = f" on `{branch}`" if alert.kind == CODE_SCANNING else ""
        return f"GitHub marks the alert fixed{where}. Closing as completed."
    if alert.auto_dismissed:
        return "A Dependabot auto-triage rule dismissed the alert. Closing as not planned."
    reason = alert.dismissed_reason or "no reason given"
    return f"The alert was dismissed on GitHub (reason: {reason}). Closing as not planned."


def plan_listed_issue(issue: Issue, alert: Alert | None, branch: str) -> Action:
    """Close an open issue once its alert is fixed or dismissed; anything else keeps it open."""
    if alert is None:
        why = f"#{issue.number}: GitHub has no {issue.key} alert; left open for a person to check"
        return Action(KEEP, issue.key, why, issue=issue)
    if alert.state == "fixed":
        why = f"{alert.name} is fixed: close #{issue.number} as completed"
        return Action(CLOSE, issue.key, why, alert=alert, issue=issue, reason=COMPLETED,
                      comment=close_comment(alert, branch))
    if alert.state == "dismissed":
        why = f"{alert.name} was dismissed: close #{issue.number} as not planned"
        return Action(CLOSE, issue.key, why, alert=alert, issue=issue, reason=NOT_PLANNED,
                      comment=close_comment(alert, branch))
    why = f"{alert.name} is {alert.state or 'in an unknown state'}: #{issue.number} stays open"
    return Action(KEEP, issue.key, why, alert=alert, issue=issue)
