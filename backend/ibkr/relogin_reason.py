"""Why did IB Gateway need a full login (phone 2FA)? (#14)

Owner: this module. Everything but ``current()`` is pure; ``current()`` reads
the newest IBC log and asks ``ibkr/windows_restarts.py`` about this boot. It
writes nothing.

IBC logs one line per Gateway start saying whether it found the saved login
Gateway leaves behind when it restarts itself at ``AutoRestartTime``:

    autorestart file found at ...: authentication will not be required
    autorestart file not found: full authentication will be required

The second one is a phone login. The saved login lives only inside the
running Gateway, so anything that ends the process -- a PC restart, a crash,
closing it -- costs one. This module names which it was, and never guesses:
without a restart on record it says the Gateway was started fresh and lists
the causes it cannot tell apart.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from constants_relogin import RELOGIN_BOOT_WINDOW_SEC, RELOGIN_SIGNIN_GAP_NOTE_SEC
from ibkr.windows_restarts import Restart

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
IBC_LOG_DIR = Path.home() / ".nova" / "ibc" / "Logs"

_STAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}):\d+ IBC: ")
_BANNER_RE = re.compile(r"Starting IBC version \S+ on .*?(\d{1,2})/(\d{1,2})/(\d{4}) at\s+(\d{1,2}):(\d{2}):(\d{2})")
_NOT_FOUND = "autorestart file not found"
_FOUND = "autorestart file found"


@dataclass(frozen=True)
class IbcLogin:
    """One Gateway start in an IBC log. ``ts`` is local epoch seconds (the
    first timestamped IBC line after the autorestart line, else the start
    banner), ``None`` when neither could be read."""

    ts: float | None
    full_auth: bool


def parse_ibc_logins(text: str) -> list[IbcLogin]:
    """Every Gateway start in one IBC log, in file order."""
    logins: list[IbcLogin] = []
    pending: bool | None = None
    banner_ts: float | None = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        low = line.lower()
        banner = _BANNER_RE.search(line)
        if banner:
            banner_ts = _banner_ts(banner)
            continue
        if low.startswith(_NOT_FOUND) or low.startswith(_FOUND):
            if pending is not None:
                logins.append(IbcLogin(ts=banner_ts, full_auth=pending))
            pending = low.startswith(_NOT_FOUND)
            continue
        stamp = _STAMP_RE.match(line)
        if stamp and pending is not None:
            logins.append(IbcLogin(ts=_local_ts(stamp.group(1)) or banner_ts, full_auth=pending))
            pending = None
    if pending is not None:
        logins.append(IbcLogin(ts=banner_ts, full_auth=pending))
    return logins


def explain(
    login: IbcLogin | None,
    restarts: list[Restart] | None,
    *,
    now: float | None = None,
) -> dict[str, Any]:
    """Why the Gateway's latest start needed (or did not need) a phone login.

    ``reason`` is ``token_reused`` (no phone needed) | ``pc_restarted`` |
    ``gateway_started_fresh`` | ``unknown``. ``restarts`` is ``None`` when the
    event log could not be read -- then a restart is never claimed.
    """
    clock = time.time() if now is None else now
    at = login.ts if login and login.ts is not None else clock
    restart = _restart_before(restarts or [], at)
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "reason": "unknown",
        "text": "",
        "login_ts": login.ts if login else None,
        "restart": restart.to_dict() if restart else None,
    }
    if login is not None and not login.full_auth:
        out["reason"] = "token_reused"
        out["text"] = (
            f"IB Gateway started at {_clock(login.ts, clock)} on its saved login -- no phone login was needed."
        )
        return out
    if restart is not None:
        out["reason"] = "pc_restarted"
        out["text"] = _restart_text(restart, clock)
        return out
    if login is not None:
        out["reason"] = "gateway_started_fresh"
        out["text"] = (
            f"IB Gateway was started fresh at {_clock(login.ts, clock)}, not by its own 11:45 PM restart, "
            "so there was no saved login to reuse. It had been closed or had crashed, a fresh login was "
            "asked for, or IBKR's weekly re-login was due."
        )
        return out
    unread = " (the Windows event log could not be read)" if restarts is None else ""
    out["text"] = f"No Gateway start is in the IBC log and no PC restart in the last day is on record{unread}."
    return out


def restart_phrase(restart: Restart, now: float) -> str:
    """``Windows Update (MoUsoCoreWorker.exe) restarted this PC at 02:29``."""
    at = _clock(restart.initiated_ts or restart.boot_ts, now)
    if restart.cause == "start_menu":
        return f"This PC was restarted from the Start menu at {at}"
    if restart.cause == "unexpected":
        return (
            "This PC came back from an unexpected shutdown (power loss, a crash or a forced "
            f"power-off) at {_clock(restart.boot_ts, now)}"
        )
    if restart.cause == "unknown":
        return f"This PC restarted at {at} (Windows recorded no reason)"
    return f"{restart.label} restarted this PC at {at}"


def _restart_text(restart: Restart, clock: float) -> str:
    text = restart_phrase(restart, clock)
    signin = restart.first_signin_ts
    if signin is not None and signin - restart.boot_ts >= RELOGIN_SIGNIN_GAP_NOTE_SEC:
        text += (
            f", and Windows waited at the sign-in screen until {_clock(signin, clock)} "
            "(Nova's morning tasks only run while you are signed in)"
        )
    elif signin is None:
        text += ", and nobody has signed in since (Nova's morning tasks only run while you are signed in)"
    return text + ". A restart ends IB Gateway's saved login, so IBKR needs your phone again."


def _restart_before(restarts: list[Restart], at: float) -> Restart | None:
    """The newest restart that booted at or before ``at`` and within the
    boot window -- older ones were survived by an 11:45 PM restart."""
    best = None
    for restart in restarts:
        if restart.boot_ts <= at + 60 and at - restart.boot_ts <= RELOGIN_BOOT_WINDOW_SEC:
            if best is None or restart.boot_ts > best.boot_ts:
                best = restart
    return best


def _clock(ts: float | None, now: float) -> str:
    if ts is None:
        return "an unknown time"
    moment = time.localtime(ts)
    today = time.localtime(now)
    hhmm = time.strftime("%H:%M", moment)
    if (moment.tm_year, moment.tm_yday) == (today.tm_year, today.tm_yday):
        return hhmm
    return f"{time.strftime('%a', moment)} {hhmm}"


def _local_ts(text: str) -> float | None:
    try:
        return time.mktime(datetime.strptime(text, "%Y-%m-%d %H:%M:%S").timetuple())
    except ValueError:
        return None


def _banner_ts(match: re.Match[str]) -> float | None:
    month, day, year, hour, minute, second = (int(g) for g in match.groups())
    try:
        return time.mktime(datetime(year, month, day, hour, minute, second).timetuple())
    except ValueError:
        return None


def current(*, log_dir: Path | None = None) -> dict[str, Any]:
    """Explain the latest Gateway start in the newest IBC log against this
    boot's restart. At most one ``wevtutil`` per boot (cached there)."""
    from ibkr import windows_restarts

    logins = parse_ibc_logins(_newest_log_text(log_dir or IBC_LOG_DIR))
    restart = windows_restarts.current_restart()
    restarts = [restart] if restart is not None else ([] if windows_restarts.boot_ts() is not None else None)
    return explain(logins[-1] if logins else None, restarts)


def _newest_log_text(directory: Path) -> str:
    try:
        logs = sorted(directory.glob("IBC-*.txt"), key=lambda p: p.stat().st_mtime)
        return logs[-1].read_text(encoding="utf-8", errors="replace") if logs else ""
    except OSError:
        logger.warning("relogin_reason: IBC log unreadable in %s", directory, exc_info=True)
        return ""
