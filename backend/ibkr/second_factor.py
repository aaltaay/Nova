"""Detect a pending/stale IBKR Second Factor (2FA) prompt from the local IBC log.

Owner: this module. Read-only -- never writes IBC config, jts.ini, or the
gateway trail.
Invalidation: nothing persisted to disk. The newest IBC log is found again
when the log folder changes, and read again -- from where the last read
stopped -- when that file grows (ADR 045: the status poll re-read and
re-scanned the whole log every 5 s on the socket loop).

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
# What a usable IBKR session reads: a logged-in Gateway has no open prompt.
NOT_PENDING = _EMPTY

_UNSET = object()
# The newest log, found again when the folder changes: (folder, its mtime_ns, newest path).
_newest_cache: tuple[Path, int, Path | None] | None = None
# What the newest log said so far: (path, bytes read, last open prompt or None).
_read_cache: tuple[Path, int, datetime | None] | None = None


def _newest_log(log_dir: Path) -> Path | None:
    global _newest_cache
    try:
        stamp = log_dir.stat().st_mtime_ns
    except OSError:
        return None
    cached = _newest_cache
    if cached is not None and cached[0] == log_dir and cached[1] == stamp:
        return cached[2]
    try:
        logs = sorted(log_dir.glob("IBC-*.txt"), key=lambda p: p.stat().st_mtime)
    except Exception:
        logger.warning("IBKR: second_factor log dir unreadable", exc_info=True)
        return None
    newest = logs[-1] if logs else None
    _newest_cache = (log_dir, stamp, newest)
    return newest


def _last_open_prompt(text: str, start: datetime | None | object = _UNSET) -> datetime | None:
    """The last ``Second Factor Authentication initiated`` with no later ``Login has completed``.

    ``start`` carries the answer for the text before this one (an incremental read)."""
    last_initiated: datetime | None = None if start is _UNSET else start  # type: ignore[assignment]
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
    return last_initiated


def parse_second_factor_state(
    text: str, *, now: datetime | None = None
) -> SecondFactorState:
    """Pure parse -- last ``Second Factor Authentication initiated`` line
    with no later ``Login has completed`` line is the currently-open prompt.
    A re-login (IBC's own timeout retry) naturally overwrites this with the
    newer attempt's timestamp.
    """
    return _state_from(_last_open_prompt(text), now)


def _state_from(last_initiated: datetime | None, now: datetime | None) -> SecondFactorState:
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

    The log decides first; the Gateway process is checked only when the log
    shows an open prompt (a prompt left behind by a Gateway that exited is
    not one the operator can act on). That check starts PowerShell, which
    blocked the HTTP loop ~265 ms on every ``/api/ibkr/status`` poll while it
    ran first (ADR 026, measured 2026-09-23). ``gateway_process_running``
    defaults to that live check -- pass it in from a caller that already
    knows the answer.
    """
    directory = log_dir or _IBC_LOG_DIR
    newest = _newest_log(directory)
    if newest is None:
        return _EMPTY
    try:
        last = _read_newest(newest)
    except Exception:
        logger.warning("IBKR: second_factor log read failed", exc_info=True)
        return _EMPTY
    state = _state_from(last, now)
    if not state.pending:
        return state
    running = (
        gateway_process_running
        if gateway_process_running is not None
        else _gateway_process_running()
    )
    return state if running else _EMPTY


def _read_newest(path: Path) -> datetime | None:
    """The log's open prompt, reading only what was appended since the last call (IBC appends)."""
    global _read_cache
    size = path.stat().st_size
    cached = _read_cache
    if cached is not None and cached[0] == path and cached[1] == size:
        return cached[2]
    start: datetime | None | object = _UNSET
    offset = 0
    if cached is not None and cached[0] == path and cached[1] < size:
        start, offset = cached[2], cached[1]
    with path.open("rb") as fh:
        fh.seek(offset)
        chunk = fh.read(size - offset)
    # Only whole lines: a line IBC is still writing is read on the next call.
    end = chunk.rfind(b"\n") + 1
    last = _last_open_prompt(chunk[:end].decode("utf-8", errors="replace"), start)
    _read_cache = (path, offset + end, last)
    return last


def _reset_for_tests() -> None:
    global _newest_cache, _read_cache
    _newest_cache = _read_cache = None


def _gateway_process_running() -> bool:
    from ibkr.launch_gateway import _gateway_process_running as _check

    return _check()
