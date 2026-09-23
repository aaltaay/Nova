"""Diagnostics row for the borrow feed (ADR 028): IBKR's short-stock file behind "Why it's moving"."""
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
from constants_move_reason import MOVE_BORROW_POLL_SEC
from diagnostics.rows import row


def borrow_feed_rows(*, status: dict[str, Any], now: float | None = None) -> list[dict[str, Any]]:
    ts = time.time() if now is None else float(now)
    last_ok = status.get("last_ok")
    stale = last_ok is None or ts - float(last_ok) > 3 * MOVE_BORROW_POLL_SEC
    if not status.get("enabled", True):
        state, detail = DIAG_STATE_OFF, "turned off (NOVA_BORROW_FEED=0)"
        cause, fix = "The borrow feed is disabled; the squeeze check reads unknown.", "Remove NOVA_BORROW_FEED=0 and restart."
    elif not status.get("running"):
        state, detail = DIAG_STATE_WARN, "not started yet"
        cause, fix = "The backend has not started the borrow feed.", "Wait a few seconds; restart the backend if it stays."
    elif str(status.get("last_error") or "").startswith("store"):
        state, detail = DIAG_STATE_FAIL, f"not recording: {status['last_error']}"
        cause = "The borrow store refused to open; only the latest poll is known and a restart loses the day."
        fix = f"Check {status.get('store')} (disk space, permissions, or a file from a newer Nova)."
    elif stale:
        state = DIAG_STATE_WARN
        detail = f"no complete poll lately{': ' + status['last_error'] if status.get('last_error') else ''}"
        cause = "IBKR's short-stock file did not answer; borrow facts are as old as the last poll."
        fix = "It retries every two minutes; check the machine's internet access (FTP to ftp2.interactivebrokers.com)."
    else:
        state, detail = DIAG_STATE_OK, f"{status.get('symbols', 0)} symbols, {status.get('polls', 0)} polls this run"
        cause, fix = "Shares to lend and borrow fees are recorded every 15 minutes.", "Nothing to do."
    return [row(id="borrow_feed", group=DIAG_GROUP_RECORDER, title="Borrow feed (IBKR short-stock file)", state=state,
                detail=detail, cause=cause, fix=fix, since=status.get("since"), evidence={**status, "checked_at": ts})]
