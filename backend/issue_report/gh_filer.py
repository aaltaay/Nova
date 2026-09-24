"""Post an issue, and its dump as a secret gist, through the GitHub CLI signed in on this PC.

``gh`` holds the operator's GitHub login (Windows Credential Manager); Nova hands it the issue
or the dump on stdin and reads back the number and the link -- it never reads or stores the
token. Every call blocks on the network, so the routes run them off the event loop.
Without ``gh``, or with ``gh`` signed out, filing is refused with a stated reason and the route
answers GitHub's prefilled new-issue link instead.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
import time
from typing import Any

from constants_issue_report import (
    ISSUE_REPORT_GH_EXE,
    ISSUE_REPORT_GH_STATUS_TTL_SEC,
    ISSUE_REPORT_GH_TIMEOUT_SEC,
    ISSUE_REPORT_REPO,
)

logger = logging.getLogger(__name__)

_NOT_INSTALLED = "the GitHub CLI (gh) is not installed on this PC"
_SIGNED_OUT = "the GitHub CLI on this PC is not signed in -- run `gh auth login` once"

_status_lock = threading.Lock()
_status_cache: tuple[float, dict[str, Any]] | None = None


class FilerError(RuntimeError):
    """Filing did not happen: ``code`` for the answer, ``message`` in plain words."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _gh(args: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    exe = shutil.which(ISSUE_REPORT_GH_EXE)
    if exe is None:
        raise FilerError("ISSUE_FILER_UNAVAILABLE", _NOT_INSTALLED)
    try:
        return subprocess.run(
            [exe, *args],
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=ISSUE_REPORT_GH_TIMEOUT_SEC,
            check=False,
            # The desk's engine may run without a console; never flash one.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise FilerError("ISSUE_FILE_FAILED",
                         f"GitHub did not answer within {ISSUE_REPORT_GH_TIMEOUT_SEC:.0f} s") from exc
    except OSError as exc:
        raise FilerError("ISSUE_FILER_UNAVAILABLE", f"the GitHub CLI could not start: {exc}") from exc


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:200]
    return ""


def _signed_out(stderr: str) -> bool:
    low = (stderr or "").lower()
    return "gh auth login" in low or "not logged in" in low or "authentication required" in low


def status(*, now: float | None = None, refresh: bool = False) -> dict[str, Any]:
    """``{direct, via, account, reason}``: whether the desk can file by itself, and as whom.

    Cached for ``ISSUE_REPORT_GH_STATUS_TTL_SEC``; a filing refreshes it."""
    global _status_cache
    now = time.time() if now is None else now
    with _status_lock:
        if not refresh and _status_cache is not None and now - _status_cache[0] < ISSUE_REPORT_GH_STATUS_TTL_SEC:
            return dict(_status_cache[1])
    try:
        done = _gh(["api", "user", "--jq", ".login"])
        if done.returncode == 0 and done.stdout.strip():
            out = {"direct": True, "via": "gh", "account": done.stdout.strip(), "reason": None}
        elif _signed_out(done.stderr):
            out = {"direct": False, "via": None, "account": None, "reason": _SIGNED_OUT}
        else:
            out = {"direct": False, "via": None, "account": None,
                   "reason": f"the GitHub CLI answered: {_first_line(done.stderr) or f'exit {done.returncode}'}"}
    except FilerError as exc:
        out = {"direct": False, "via": None, "account": None, "reason": exc.message}
    with _status_lock:
        _status_cache = (now, out)
    return dict(out)


def file_issue(title: str, body: str, labels: list[str]) -> dict[str, Any]:
    """Create the issue; ``{number, url}`` or ``FilerError``."""
    payload = json.dumps({"title": title, "body": body, "labels": labels})
    done = _gh(["api", "--method", "POST", f"repos/{ISSUE_REPORT_REPO}/issues", "--input", "-"], stdin=payload)
    if done.returncode != 0:
        if _signed_out(done.stderr):
            status(refresh=True)
            raise FilerError("ISSUE_FILER_UNAVAILABLE", _SIGNED_OUT)
        detail = _first_line(done.stderr) or f"exit {done.returncode}"
        logger.warning("issue_report: gh api refused the issue: %s", detail)
        raise FilerError("ISSUE_FILE_FAILED", f"GitHub refused the issue: {detail}")
    try:
        created = json.loads(done.stdout)
        number, url = int(created["number"]), str(created["html_url"])
    except (ValueError, KeyError, TypeError) as exc:
        # The issue may exist; say so rather than invite a duplicate.
        logger.warning("issue_report: gh api answered without a readable issue: %.200s", done.stdout)
        raise FilerError("ISSUE_FILE_UNCONFIRMED",
                         "GitHub answered, but Nova could not read which issue it made -- check the "
                         "repository's issues before filing again") from exc
    return {"number": number, "url": url}


_GIST_URL = re.compile(r"https://gist\.github\.com/\S+")


def create_gist(file_name: str, text: str, description: str) -> str:
    """Upload the dump as a secret (unlisted) gist; its URL or ``FilerError``."""
    done = _gh(["gist", "create", "--filename", file_name, "--desc", description, "-"], stdin=text)
    if done.returncode != 0:
        if _signed_out(done.stderr):
            status(refresh=True)
            raise FilerError("ISSUE_FILER_UNAVAILABLE", _SIGNED_OUT)
        detail = _first_line(done.stderr) or f"exit {done.returncode}"
        logger.warning("issue_report: gh gist create failed: %s", detail)
        raise FilerError("ISSUE_FILE_FAILED", f"GitHub refused the dump: {detail}")
    urls = _GIST_URL.findall(done.stdout or "")
    if not urls:
        logger.warning("issue_report: gh gist create answered without a URL: %.200s", done.stdout)
        raise FilerError("ISSUE_FILE_FAILED", "GitHub answered, but without the dump's link")
    return urls[-1]


def reset_for_tests() -> None:
    global _status_cache
    with _status_lock:
        _status_cache = None
