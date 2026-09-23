"""Diagnostics row for the live catalyst feed (ADR 024)."""
from __future__ import annotations

import time
from typing import Any

from constants_diagnostics import (
    DIAG_GROUP_RECORDER,
    DIAG_STATE_FAIL,
    DIAG_STATE_OFF,
    DIAG_STATE_OK,
    DIAG_STATE_WARN,
)
from diagnostics.rows import row


def catalyst_feed_rows(*, status: dict[str, Any], now: float | None = None) -> list[dict[str, Any]]:
    ts = time.time() if now is None else float(now)
    sources = status.get("sources") or {}
    covering = sorted(n for n, s in sources.items() if s.get("covering_since"))
    failing = sorted(n for n, s in sources.items() if s.get("last_error"))
    if not status.get("enabled", True):
        state, detail = DIAG_STATE_OFF, "turned off (NOVA_CATALYST_FEED=0)"
        cause, fix = "The live catalyst feed is disabled.", "Remove NOVA_CATALYST_FEED=0 from .env and restart."
    elif not status.get("running"):
        state, detail = DIAG_STATE_WARN, "not started yet"
        cause, fix = "The backend has not started the catalyst feed loop.", "Wait a few seconds; restart the backend if it stays."
    elif str(status.get("error") or "").startswith("store"):
        state, detail = DIAG_STATE_FAIL, f"recording in memory only: {status['error']}"
        cause = "The feed store refused a write; today's items survive only until the backend restarts."
        fix = f"Check the drive holding {status.get('store')} (mounted, space, permissions)."
    elif failing:
        state, detail = DIAG_STATE_WARN, f"reading {', '.join(covering) or 'nothing'}; failing: {', '.join(failing)}"
        cause = "A catalyst source did not answer; its coverage has a gap, so no-news verdicts there stay unknown."
        fix = "It retries on its own; check the machine's internet access if it persists."
    else:
        state, detail = DIAG_STATE_OK, f"reading {', '.join(covering) or 'sources (first round in progress)'}"
        cause, fix = "SEC filings and the press-release wires are recorded as they publish.", "Nothing to do."
    return [row(
        id="catalyst_feed",
        group=DIAG_GROUP_RECORDER,
        title="Catalyst feed (SEC + wires)",
        state=state,
        detail=detail,
        cause=cause,
        fix=fix,
        since=status.get("since"),
        evidence={**status, "checked_at": ts},
    )]
