"""Filing a GitHub issue from the desk (operator ask, 2026-09-24): tunables.

Owner: ``issue_report/``. Schema: AGENTS.md §3, "Filing an issue from the desk".
"""
from __future__ import annotations

ISSUE_REPORT_SCHEMA_VERSION = 1
# Where the desk files. Public: everything filed there can be read by anyone.
ISSUE_REPORT_REPO = "aaltaay/Nova"
ISSUE_REPORT_NEW_URL = f"https://github.com/{ISSUE_REPORT_REPO}/issues/new"

# kind -> (what the form calls it, the GitHub label the backlog triage reads)
ISSUE_REPORT_KINDS: dict[str, tuple[str, str]] = {
    "bug": ("Bug", "bug"),
    "feature": ("Feature", "enhancement"),
}

ISSUE_REPORT_TITLE_MAX = 120
ISSUE_REPORT_DETAILS_MAX = 8000
# The prefilled new-issue link carries the body in its query; GitHub refuses
# very long URLs, so a long body is cut to this many characters there.
ISSUE_REPORT_URL_BODY_MAX = 4000
ISSUE_REPORT_BODY_MAX_BYTES = 32_000

# The GitHub CLI the desk files through (it holds the operator's login; Nova never reads the token).
ISSUE_REPORT_GH_EXE = "gh"
ISSUE_REPORT_GH_TIMEOUT_SEC = 30.0
# `gh auth status` is asked at most this often for the form's "files as ..." line.
ISSUE_REPORT_GH_STATUS_TTL_SEC = 300.0

# The dump: what the desk attaches (uploaded as a secret gist, linked from the issue).
ISSUE_REPORT_DUMP_SCHEMA_VERSION = 1
ISSUE_REPORT_LOG_TAIL_BYTES = 2_000_000          # read this much of the engine log's end
ISSUE_REPORT_LOG_RECORDS = 50                    # distinct warnings / errors kept (repeats folded)
ISSUE_REPORT_CLIENT_ERRORS = 20                  # errors the desk windows reported
ISSUE_REPORT_LOG_LINE_MAX = 500                  # characters of one record kept
ISSUE_REPORT_DUMP_MAX_CHARS = 200_000
# The diagnostics groups whose evidence is about this PC (paths, key names), not the desk's state.
ISSUE_REPORT_PRIVATE_EVIDENCE_GROUPS = ("process", "integrations")
ISSUE_REPORT_DRAFT_TTL_SEC = 1800.0              # a draft's dump stays filable this long
ISSUE_REPORT_DRAFTS_KEEP = 8
ISSUE_REPORT_DUMP_DIR = "issue_dumps"            # under the operator cache: a copy of every dump
# Auto-written text when the operator types nothing.
ISSUE_REPORT_AUTO_ROWS = 8
ISSUE_REPORT_AUTO_LOG_RECORDS = 5
ISSUE_REPORT_AUTO_CLIENT_ERRORS = 3

# Environment names whose values are secrets: never posted, whatever the operator pastes.
ISSUE_REPORT_SECRET_NAME_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASSWD", "PIN", "HASH")
# Shorter values are too likely to appear in ordinary words to redact safely.
ISSUE_REPORT_SECRET_MIN_LEN = 8
ISSUE_REPORT_REDACTED = "[redacted]"
