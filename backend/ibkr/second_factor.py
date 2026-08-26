"""Detect a pending/stale IBKR Second Factor (2FA) prompt from the local IBC log.

Owner: this module. Read-only -- never writes IBC config, jts.ini, or the
gateway trail.
Invalidation: nothing persisted to disk; every call re-reads the newest IBC
log file, so state always reflects the current log tail.

Why this exists (PROBLEM_LOG 2026-08-25): IBC timestamps a Second Factor
Authentication prompt when it opens, and once it finally closes -- whether
because the operator approved it or because IBKR itself timed it out --
IBC compares the elapsed time to its own ``SecondFactorAuthenticationTimeout``
(180s). If that elapsed time is over the limit, IBC discards the login and
starts a fresh one, even though the operator just approved it. From the
operator's chair this looks like "I approved 2FA and it did nothing" --
the fix is to detect that the prompt on screen is already too old to be
honored, and offer a one-click restart instead of a second silent failure.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from constants_ibkr import IBKR_SECOND_FACTOR_STALE_AFTER_SEC

logger = logging.getLogger(__name__)

_IBC_LOG_DIR = Path.home() / ".nova" / "ibc" / "Logs"
_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}):\d+ IBC: (.+)$")
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class SecondFactorState:
    """``pending`` is only true while the Gateway window is actually up --
    a prompt that lingers in the log after the whole process exits is not a
    prompt an operator can act on; the ordinary launch_gateway CTA covers
    that case instead."""

    pending: bool
    age_sec: float | None
    stale: bool


_EMPTY = SecondFactorState(pending=False, age_sec=None, stale=False)


def _newest_log(log_dir: Path) -> Path | None:
    try:
        logs = sorted(log_dir.glob("IBC-*.txt"), key=lambda p: p.stat().st_mtime)
    except Exception:
        logger.warning("IBKR: second_factor log dir unreadable", exc_info=True)
        return None
    return logs[-1] if logs else None


def parse_second_factor_state(
    text: str, *, now: datetime | None = None
) -> SecondFactorState:
    """Pure parse -- last ``Second Factor Authentication initiated`` line
    with no later ``Login has completed`` line is the currently-open prompt.
    A re-login (IBC's own timeout retry) naturally overwrites this with the
    newer attempt's timestamp.
    """
    last_initiated: datetime | None = None
    for raw in text.splitlines():
        m = _LINE_RE.match(raw.strip())
        if not m:
            continue
        ts_text, rest = m.groups()
        low = rest.lower()
        if "second factor authentication initiated" in low:
            try:
                last_initiated = datetime.strptime(ts_text, _TS_FORMAT)
            except ValueError:
                continue
        elif "login has completed" in low:
            last_initiated = None
    if last_initiated is None:
        return _EMPTY
    clock = now or datetime.now()
    age = max(0.0, (clock - last_initiated).total_seconds())
    return SecondFactorState(
        pending=True,
        age_sec=age,
        stale=age > IBKR_SECOND_FACTOR_STALE_AFTER_SEC,
    )


def current_state(
    *,
    log_dir: Path | None = None,
    now: datetime | None = None,
    gateway_process_running: bool | None = None,
) -> SecondFactorState:
    """Read the newest IBC log and report the live 2FA prompt state.

    ``gateway_process_running`` defaults to a live check -- pass it in from
    a caller that already knows the answer to avoid a redundant probe.
    """
    running = (
        gateway_process_running
        if gateway_process_running is not None
        else _gateway_process_running()
    )
    if not running:
        return _EMPTY
    directory = log_dir or _IBC_LOG_DIR
    newest = _newest_log(directory)
    if newest is None:
        return _EMPTY
    try:
        text = newest.read_text(encoding="utf-8", errors="replace")
    except Exception:
        logger.warning("IBKR: second_factor log read failed", exc_info=True)
        return _EMPTY
    return parse_second_factor_state(text, now=now)


def _gateway_process_running() -> bool:
    from ibkr.launch_gateway import _gateway_process_running as _check

    return _check()
