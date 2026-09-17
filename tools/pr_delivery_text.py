"""Pure squash-merge fields and conflict-comment text for PR delivery."""

from __future__ import annotations

CONFLICT_COMMENT_MARKER = "<!-- nova-pr-delivery-conflict -->"
SQUASH_BODY_MAX = 4000
SQUASH_TITLE_MAX = 256


def squash_commit_title(number: int, title: str) -> str:
    line = (title or "").strip().splitlines()[0].strip()
    if not line:
        line = f"#{int(number)}"
    return line[:SQUASH_TITLE_MAX]


def squash_merge_fields(number: int, title: str, body: str = "") -> dict[str, str]:
    fields = {
        "merge_method": "squash",
        "commit_title": squash_commit_title(number, title),
    }
    text = (body or "").strip()
    if text:
        if len(text) > SQUASH_BODY_MAX:
            text = text[:SQUASH_BODY_MAX].rstrip() + "\n..."
        fields["commit_message"] = text
    return fields


def conflict_rebase_comment() -> str:
    return (
        f"{CONFLICT_COMMENT_MARKER}\n"
        "**PR delivery: conflicts with `origin/master`**\n"
        "\n"
        "This PR is dirty/conflicting, so Auto-merge will not squash-merge it.\n"
        "\n"
        "Cursor cloud agent: rebase onto latest `origin/master`, resolve "
        "conflicts, push, and leave the PR ready (non-draft). Do not leave "
        "this PR silent.\n"
        "\n"
        "```text\n"
        "git fetch origin master\n"
        "git rebase origin/master\n"
        "# resolve conflicts, then:\n"
        "git push --force-with-lease\n"
        "```\n"
        "\n"
        "Force-with-lease is only for this PR head after rebase. "
        "Do not force-push `master`. Do not change required check names.\n"
    )


def should_post_conflict_comment(existing_bodies: list[str]) -> bool:
    return not any(CONFLICT_COMMENT_MARKER in (body or "") for body in existing_bodies)
