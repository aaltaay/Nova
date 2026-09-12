#!/usr/bin/env python3
"""Publish AI news digest site files via a ready PR. Never push master.

Scheduled ``AI news digest`` used to ``git commit`` + ``git push`` on
``master``. Required status checks reject that (GH006). This helper
commits on ``chore/ai-news-digest`` and create-or-updates a non-draft PR.

Usage:
  python3 tools/ai_news_digest_pr.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Callable

DIGEST_PATHS: tuple[str, ...] = (
    "site/index.html",
    "site/news/index.html",
    "site/news/feed.json",
)
DIGEST_BRANCH = "chore/ai-news-digest"
BASE_BRANCH = "master"
COMMIT_MESSAGE = "chore(site): refresh AI-in-trading news feed"
PR_TITLE = COMMIT_MESSAGE
PR_BODY = """Automated marketing-site digest refresh.

Updates `site/index.html`, `site/news/index.html`, and `site/news/feed.json`.

Opened by `.github/workflows/ai-news.yml` so the job never pushes `master`
(GH006 -- required status checks). Empty rebuilds exit 0 without a PR.
"""
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"

PROTECTED_PUSH_REFS = frozenset(
    {
        "master",
        "main",
        "HEAD",
        "refs/heads/master",
        "refs/heads/main",
    }
)

EXIT_OK = 0
EXIT_ERROR = 1

Runner = Callable[..., subprocess.CompletedProcess[str]]


def assert_push_ref_allowed(ref: str) -> None:
    name = (ref or "").strip()
    if not name:
        raise ValueError("refusing to push digest to an empty ref")
    if name in PROTECTED_PUSH_REFS or name.endswith("/master") or name.endswith("/main"):
        raise ValueError(f"refusing to push digest to {ref}")


def push_command(branch: str) -> list[str]:
    assert_push_ref_allowed(branch)
    return ["git", "push", "--force", "-u", "origin", branch]


def status_command() -> list[str]:
    return ["git", "status", "--porcelain", "--", *DIGEST_PATHS]


def pr_list_command() -> list[str]:
    return [
        "gh",
        "pr",
        "list",
        "--head",
        DIGEST_BRANCH,
        "--base",
        BASE_BRANCH,
        "--state",
        "open",
        "--json",
        "number,url,isDraft",
    ]


def pr_create_command() -> list[str]:
    return [
        "gh",
        "pr",
        "create",
        "--base",
        BASE_BRANCH,
        "--head",
        DIGEST_BRANCH,
        "--title",
        PR_TITLE,
        "--body",
        PR_BODY,
    ]


def pr_ready_command(number: int) -> list[str]:
    return ["gh", "pr", "ready", str(number)]


def _run(cmd: list[str], runner: Runner) -> subprocess.CompletedProcess[str]:
    return runner(cmd, check=False, capture_output=True, text=True)


def _ok(result: subprocess.CompletedProcess[str], what: str) -> None:
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{what} failed: {err}")


def parse_open_prs(raw: str) -> list[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise RuntimeError("gh pr list returned a non-list")
    return [row for row in data if isinstance(row, dict)]


def publish(*, runner: Runner | None = None) -> int:
    run = runner or subprocess.run
    status = _run(status_command(), run)
    _ok(status, "git status")
    if not status.stdout.strip():
        print("No change to the digest.")
        return EXIT_OK

    _ok(_run(["git", "config", "--local", "user.name", BOT_NAME], run), "git config user.name")
    _ok(_run(["git", "config", "--local", "user.email", BOT_EMAIL], run), "git config user.email")
    _ok(_run(["git", "checkout", "-B", DIGEST_BRANCH], run), "git checkout")
    _ok(_run(["git", "add", "--", *DIGEST_PATHS], run), "git add")
    commit = _run(["git", "commit", "-m", COMMIT_MESSAGE], run)
    if commit.returncode != 0:
        combined = f"{commit.stdout} {commit.stderr}"
        if "nothing to commit" in combined.lower():
            print("No change to the digest.")
            return EXIT_OK
        _ok(commit, "git commit")

    push = _run(push_command(DIGEST_BRANCH), run)
    _ok(push, "git push digest branch")

    listed = _run(pr_list_command(), run)
    _ok(listed, "gh pr list")
    open_prs = parse_open_prs(listed.stdout)
    if open_prs:
        number = int(open_prs[0]["number"])
        url = str(open_prs[0].get("url") or f"#{number}")
        if open_prs[0].get("isDraft"):
            _ok(_run(pr_ready_command(number), run), "gh pr ready")
        print(f"Updated existing digest PR {url}")
        return EXIT_OK

    created = _run(pr_create_command(), run)
    _ok(created, "gh pr create")
    print((created.stdout or "Opened digest PR").strip())
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    del argv  # no flags -- workflow calls this with no args
    try:
        return publish()
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
