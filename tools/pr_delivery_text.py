"""Pure squash-merge fields and conflict-comment text for PR delivery."""

from __future__ import annotations

import re

CONFLICT_COMMENT_MARKER = "<!-- nova-pr-delivery-conflict -->"
SQUASH_BODY_MAX = 4000
SQUASH_TITLE_MAX = 256


def squash_commit_title(number: int, title: str) -> str:
    raw = (title or "").strip()
    line = raw.splitlines()[0].strip() if raw else ""
    if not line:
        line = f"#{int(number)}"
    return line[:SQUASH_TITLE_MAX]


def squash_merge_fields(
    number: int, title: str, body: str = "", sha: str = "",
) -> dict[str, str]:
    """`sha` binds the merge to the head the decision was made about (#412).

    Without it the payload binds to the PR *number*, so a push landing between
    the last fetch and this PUT is merged as-is -- a head that never passed the
    settling floor or the in-flight-review check.
    """
    fields = {
        "merge_method": "squash",
        "commit_title": squash_commit_title(number, title),
    }
    if sha:
        fields["sha"] = sha
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


_CLOSING_KEYWORD = r"(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)"
_CLOSING_LINE = re.compile(r"^ {0,3}(?:[-*+]\s+)?" + _CLOSING_KEYWORD + r"\b", re.I)
_CLOSING_REFERENCE = re.compile(
    r"\b" + _CLOSING_KEYWORD + r"\b:?\s+"
    r"(?:#(?P<bare>[1-9]\d*)|"
    r"(?P<repo>[\w.-]+/[\w.-]+)#(?P<qualified>[1-9]\d*)|"
    r"https://github\.com/(?P<url_repo>[\w.-]+/[\w.-]+)/issues/(?P<url_number>[1-9]\d*))"
    r"(?=$|[\s,;.)])",
    re.I,
)


def closing_issue_numbers(body: str, repo: str) -> list[int]:
    """Explicit completion lines only; never infer closure from prose/examples.

    Use the full PR body, not its truncated squash message. Each issue needs
    its own closing keyword, as in GitHub's documented multiple-issue syntax.
    """
    text = re.sub(r"<!--.*?-->", "", body or "", flags=re.S)
    numbers: list[int] = []
    fence = ""
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = ""
            continue
        if fence or not _CLOSING_LINE.match(line):
            continue
        line = re.sub(r"`+[^`]*`+", "", line)
        # A completion line may list several keyword/reference pairs. Stop
        # at prose rather than treating its incidental mentions as completion.
        line = re.sub(r"^ {0,3}(?:[-*+]\s+)?", "", line)
        while match := _CLOSING_REFERENCE.match(line):
            target = match.group("repo") or match.group("url_repo") or repo
            if target.casefold() == repo.casefold():
                number = int(match.group("bare") or match.group("qualified") or match.group("url_number"))
                if number not in numbers:
                    numbers.append(number)
            tail = line[match.end():]
            separator = re.match(r"(?:[,;]\s*(?:and\s+)?|\s+and\s+)", tail, re.I)
            if not separator:
                break
            line = tail[separator.end():]
    return numbers
