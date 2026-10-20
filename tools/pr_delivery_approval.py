"""Owner approval for auto-merge.

The label ``merge-approved`` is not proof. A bot or an agent with a write
token can add it. Merge only when the pull request currently has that label
and the most recent ``labeled`` event for it, on the issue events API, was
by GitHub user ``aaltaay``. An unreadable timeline does not merge. This
module never removes the label.

``GET /repos/{owner}/{repo}/issues/{number}/events`` is the events feed of
the issue timeline. Each ``labeled`` item carries ``actor.login``.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

try:
    from tools.release_gate import documents
except ImportError:  # `python tools/pr_delivery.py` puts tools/ on sys.path
    from release_gate import documents

OWNER_LOGIN = "aaltaay"
MERGE_APPROVED_LABEL = "merge-approved"
ACTOR_COMMENT_MARKER = "<!-- nova-merge-approved-actor -->"

REASON_MISSING = "merge-approved-missing"
REASON_ACTOR = "merge-approved-actor"
REASON_UNVERIFIED = "merge-approved-unverified"
REASON_OK = "ok"

GhFn = Callable[..., Any]


def _label_names(labels: Any) -> set[str]:
    try:
        from tools.pr_delivery import label_names
    except ImportError:
        from pr_delivery import label_names
    return label_names(labels)


def _event_label(event: dict[str, Any]) -> str:
    label = event.get("label")
    if isinstance(label, dict):
        return str(label.get("name") or "")
    if isinstance(label, str):
        return label
    return ""


def parse_issue_events(text: str) -> list[dict[str, Any]]:
    """Pages from ``gh api --paginate`` of the issue events list."""
    events: list[dict[str, Any]] = []
    for doc in documents(text or ""):
        if isinstance(doc, list):
            events.extend(item for item in doc if isinstance(item, dict))
        elif isinstance(doc, dict) and isinstance(doc.get("event"), str):
            events.append(doc)
    return events


def latest_labeled_actor(
    events: list[dict[str, Any]], label: str = MERGE_APPROVED_LABEL,
) -> str | None:
    """Login that most recently added ``label``, or None if that event is absent.

    ``created_at`` orders the events. The same timestamp keeps the later
    entry, which is the newer one when GitHub returns oldest first.
    """
    best_key: tuple[str, int] | None = None
    best_login: str | None = None
    for index, event in enumerate(events):
        if str(event.get("event") or "").lower() != "labeled":
            continue
        if _event_label(event).lower() != label.lower():
            continue
        created = str(event.get("created_at") or event.get("createdAt") or "")
        key = (created, index)
        if best_key is not None and key < best_key:
            continue
        actor = event.get("actor") or {}
        login = str(actor.get("login") or "") if isinstance(actor, dict) else str(actor or "")
        best_key = key
        best_login = login
    return best_login


def owner_merge_approval(
    has_label: bool, events: list[dict[str, Any]] | None,
) -> tuple[bool, str, str]:
    """``(approved, reason, actor)``.

    ``events is None`` means the issue events API could not be read. An empty
    list was read and never recorded this label. Both refuse the merge.
    """
    if not has_label:
        return False, REASON_MISSING, ""
    if events is None:
        return False, REASON_UNVERIFIED, ""
    actor = latest_labeled_actor(events)
    if actor is None or not actor.strip():
        return False, REASON_UNVERIFIED, ""
    if actor.casefold() != OWNER_LOGIN.casefold():
        return False, REASON_ACTOR, actor
    return True, REASON_OK, actor


def fetch_label_events(gh: GhFn, repo: str, number: int) -> list[dict[str, Any]] | None:
    """Issue events API. None when the read fails (fail closed)."""
    if number <= 0 or not str(repo or "").strip():
        return None
    proc = gh(
        ["api", "--paginate", f"repos/{repo}/issues/{number}/events?per_page=100"],
        check=False,
    )
    if getattr(proc, "returncode", 1) != 0:
        return None
    try:
        return parse_issue_events(getattr(proc, "stdout", "") or "")
    except (ValueError, TypeError):
        return None


def approval_for_pr(pr: dict[str, Any], *, gh: GhFn, repo: str) -> tuple[bool, str, str]:
    """Current labels first. A removed label does not merge.

    ``label_events`` on ``pr`` is a test double. Production payloads omit it
    and this reads the issue events API.
    """
    has_label = MERGE_APPROVED_LABEL in _label_names(pr.get("labels"))
    if not has_label:
        return owner_merge_approval(False, None)
    if "label_events" in pr:
        events = pr.get("label_events")
        if not isinstance(events, list):
            events = None
        return owner_merge_approval(True, events)
    number = int(pr.get("number") or 0)
    return owner_merge_approval(True, fetch_label_events(gh, repo, number))


def wrong_actor_comment(actor: str) -> str:
    who = (actor or "").strip() or "someone else"
    return (
        f"{ACTOR_COMMENT_MARKER}\n"
        f"**Not merged: `merge-approved` was added by `{who}`, not `{OWNER_LOGIN}`.**\n"
        "\n"
        "Auto-merge merges only when that label is on the pull request and the "
        f"most recent labeled event for it was by `{OWNER_LOGIN}`. "
        "The label was left in place. Agents never add `merge-approved`; only the owner does.\n"
    )


def should_post_actor_comment(existing_bodies: list[str], body: str) -> bool:
    wanted = body.strip()
    return not any((item or "").strip() == wanted for item in existing_bodies)


def signal_wrong_actor(gh: GhFn, repo: str, number: int, actor: str) -> None:
    """One short comment. Does not remove the label."""
    body = wrong_actor_comment(actor)
    listed = gh(
        ["api", "--paginate", f"repos/{repo}/issues/{number}/comments?per_page=100"],
        check=False,
    )
    if getattr(listed, "returncode", 1) != 0:
        print(
            getattr(listed, "stderr", "") or f"#{number} comments unreadable; not posting",
            file=sys.stderr,
        )
        return
    bodies: list[str] = []
    try:
        for page in documents(getattr(listed, "stdout", "") or ""):
            if isinstance(page, list):
                bodies.extend(
                    str(item.get("body") or "")
                    for item in page
                    if isinstance(item, dict)
                )
    except (ValueError, TypeError) as exc:
        print(f"#{number} comments unreadable ({exc}); not posting", file=sys.stderr)
        return
    if not should_post_actor_comment(bodies, body):
        print(f"#{number} actor comment already present")
        return
    posted = gh(["pr", "comment", str(number), "--body", body], check=False)
    if getattr(posted, "returncode", 1) != 0:
        print(
            getattr(posted, "stderr", "") or getattr(posted, "stdout", "")
            or f"actor comment #{number} failed",
            file=sys.stderr,
        )
        return
    print(f"#{number} actor comment posted")
