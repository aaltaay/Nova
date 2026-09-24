"""What the desk attaches to an issue, and what it must never post.

``gather`` reads memory only: Nova's revision (read once at import by ``diagnostics``), the
desk venue and the window in front from the focus sensor (ADR 033). ``scrubber`` builds the one
``scrub.Scrubber`` everything posted passes through, from what this process knows about the PC:
the secret-named environment values, the IBKR account ids, the repo / data / home folders, the
user and machine names.
"""
from __future__ import annotations

import getpass
import logging
import os
import socket
from pathlib import Path
from typing import Any

from constants_data_root import DATA_CACHE_TARGET_WIN
from constants_issue_report import ISSUE_REPORT_SECRET_MIN_LEN, ISSUE_REPORT_SECRET_NAME_MARKERS
from issue_report.scrub import Scrubber

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def gather() -> dict[str, Any]:
    """``{nova, commit, ui, venue, page, tab, symbol}``; each ``None`` when unknown."""
    out: dict[str, Any] = dict.fromkeys(("nova", "commit", "ui", "venue", "page", "tab", "symbol"))
    try:
        from diagnostics.process_info import REVISION

        out["nova"], out["commit"] = REVISION.get("release_tag"), REVISION.get("commit")
    except Exception:
        logger.warning("issue_report: Nova's revision is unreadable", exc_info=True)
    try:
        from sim.mode import venue

        out["venue"] = venue()
    except Exception:
        logger.warning("issue_report: the desk venue is unreadable", exc_info=True)
    try:
        from sensors import focus_store

        focus = focus_store.resolve()
        out["page"], out["tab"], out["symbol"] = focus.get("page"), focus.get("tab"), focus.get("symbol")
        front = next((w for w in focus.get("windows") or [] if w.get("window_id") == focus.get("window_id")), None)
        out["ui"] = (front or {}).get("ui_tag")
    except Exception:
        logger.warning("issue_report: the focus sensor is unreadable", exc_info=True)
    return out


def secret_values() -> list[str]:
    """Values never to post: secret-named environment values and the IBKR account ids."""
    values = [
        value.strip()
        for name, value in os.environ.items()
        if any(marker in name.upper() for marker in ISSUE_REPORT_SECRET_NAME_MARKERS)
        and len(value.strip()) >= ISSUE_REPORT_SECRET_MIN_LEN
    ]
    try:
        from ibkr import client

        values += client.managed_account_ids()
    except Exception:
        # The account-id pattern in the scrubber still applies.
        logger.warning("issue_report: IBKR account ids are unreadable", exc_info=True)
    return values


def _roots() -> list[tuple[str, str]]:
    roots = [(str(_REPO_ROOT), "<repo>"), (str(Path(DATA_CACHE_TARGET_WIN).parent), "<data>")]
    try:
        from paths import cache_dir, log_dir

        roots += [(str(cache_dir()), "<cache>"), (str(log_dir()), "<logs>")]
        roots += [(os.path.realpath(cache_dir()), "<cache>"), (os.path.realpath(log_dir()), "<logs>")]
    except Exception:
        logger.warning("issue_report: the cache / log folders are unreadable", exc_info=True)
    roots.append((str(Path.home()), "<home>"))
    return roots


def _name(read: Any) -> str | None:
    try:
        return str(read()) or None
    except Exception:
        # Unknown: the path and e-mail rules still apply.
        logger.warning("issue_report: a name to scrub is unreadable", exc_info=True)
        return None


def scrubber() -> Scrubber:
    """A fresh scrubber for one pass (its count starts at zero)."""
    return Scrubber(secrets=secret_values(), roots=_roots(), user=_name(getpass.getuser),
                    host=_name(socket.gethostname))
