"""The desk's planned stop: log why, then leave through uvicorn's own shutdown (``POST /api/diagnostics/stop``).

A force-kill (``scripts/Stop-NovaPorts.ps1``) skips the lifespan's shutdown: no log line says why the API went,
recordings are finalized from disk as interrupted at the next start, and the leaderboard calls the gap
"unexpected". On 2026-10-13 both "Restart to update" restarts (07:51, 08:45 ET) read as crashes for that reason.
Asking uvicorn to exit the way Ctrl+C does runs the shutdown: the leaderboard run ends ``shutdown`` and the
captures close. The desk still force-kills if the port is not free in time (``engineRestart.mjs``).
"""
from __future__ import annotations

import asyncio
import logging
import signal

from constants_diagnostics import DIAG_STOP_DELAY_SEC, DIAG_STOP_REASON_MAX_CHARS

logger = logging.getLogger(__name__)


def clean_reason(reason: str | None) -> str:
    """One printable line, at most ``DIAG_STOP_REASON_MAX_CHARS``; empty reads ``unstated``."""
    text = " ".join(str(reason or "").split())[:DIAG_STOP_REASON_MAX_CHARS]
    return text or "unstated"


def _exit_like_ctrl_c() -> None:
    # uvicorn handles SIGINT by setting should_exit: the lifespan shutdown runs, then the process exits.
    signal.raise_signal(signal.SIGINT)


def request_stop(reason: str | None) -> dict:
    """Log the reason and schedule the exit on the running loop; the caller's reply goes out first."""
    why = clean_reason(reason)
    logger.warning("API: stopping at the desk's request -- %s", why)
    asyncio.get_running_loop().call_later(DIAG_STOP_DELAY_SEC, _exit_like_ctrl_c)
    return {"ok": True, "stopping": True, "reason": why}
