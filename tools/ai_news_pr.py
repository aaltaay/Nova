"""Open or update the marketing-site digest PR. Never push master.

The scheduled Action runs `ai_news_digest.py`, then this script. If the
static files changed, they land on `chore/ai-news-digest` and a PR so
required CI can pass. Direct master push is how Vercel and branch
protection fought each other.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIGEST_BRANCH = "chore/ai-news-digest"
DIGEST_PATHS = (
    "site/index.html",
    "site/news/index.html",
    "site/news/feed.json",
)
PR_TITLE = "chore(site): refresh AI-in-trading news feed"
PR_BODY = """## What

Refresh the public `/news` AI-in-trading feed (static HTML/JSON).

## Why this approach

Digest updates must pass required CI. They must not push `master` directly.

## Verified by

`pytest tools/test_ai_news_digest.py` in the digest workflow.

## Related issue

Refs #106
"""


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )


def changed_digest_paths() -> list[str]:
    listed = _git("diff", "--name-only", "--", *DIGEST_PATHS)
    return [line.strip() for line in listed.stdout.splitlines() if line.strip()]


def main() -> int:
    dirty = changed_digest_paths()
    if not dirty:
        print("No digest file changes.")
        return 0

    _git("config", "user.name", "github-actions[bot]")
    _git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    checkout = _git("checkout", "-B", DIGEST_BRANCH)
    if checkout.returncode != 0:
        print(checkout.stderr, file=sys.stderr)
        return checkout.returncode

    add = _git("add", "--", *DIGEST_PATHS)
    if add.returncode != 0:
        print(add.stderr, file=sys.stderr)
        return add.returncode

    commit = _git("commit", "-m", PR_TITLE)
    if commit.returncode != 0:
        print(commit.stderr, file=sys.stderr)
        return commit.returncode

    push = _git("push", "--force", "-u", "origin", DIGEST_BRANCH)
    if push.returncode != 0:
        print(push.stderr, file=sys.stderr)
        return push.returncode

    existing = subprocess.run(
        ["gh", "pr", "list", "--head", DIGEST_BRANCH, "--state", "open", "--json", "number"],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    if existing.returncode == 0 and existing.stdout.strip() not in ("[]", ""):
        print("Updated open digest PR.")
        return 0

    created = subprocess.run(
        [
            "gh", "pr", "create",
            "--title", PR_TITLE,
            "--body", PR_BODY,
            "--base", "master",
            "--head", DIGEST_BRANCH,
        ],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    if created.returncode != 0:
        print(created.stderr, file=sys.stderr)
        return created.returncode
    print(created.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
