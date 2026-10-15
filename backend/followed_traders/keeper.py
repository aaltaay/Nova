"""The keeper: when the feed stops, Nova starts it again (operator ask 2026-10-14).

"What do we do in the situations where the server shuts down? We need an auto-recovery, a part of the backend with
Nova." The feed is another program on this machine. Nova never runs its code: it runs the Windows scheduled task named
by ``NOVA_FOLLOW_FEED_TASK``, whose own script starts whatever part of the feed is not running and leaves alone what
is. The task runs outside Nova's processes, so the feed outlives a restart or an update of Nova.

``decide`` is the rule (pure); ``tick`` asks the feed once and runs the task when the rule says so; ``run`` is the
loop the backend starts; ``view`` is what ``/day`` carries as ``keeper``. Schema: architecture/schema/followed-traders.md
("Starting the feed again when it stops").
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from followed_traders import config, feed
from followed_traders.constants_followed import (
    FOLLOWED_FEED_TASK_ENV,
    FOLLOWED_KEEPER_CAPTURE_FROM_ET,
    FOLLOWED_KEEPER_CAPTURE_UNTIL_ET,
    FOLLOWED_KEEPER_COOLDOWN_SEC,
    FOLLOWED_KEEPER_DOWN_SEC,
    FOLLOWED_KEEPER_HOSTS,
    FOLLOWED_KEEPER_RUN_TIMEOUT_SEC,
    FOLLOWED_KEEPER_STALE_SEC,
    FOLLOWED_KEEPER_TICK_SEC,
)

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
_warned: set[str] = set()

_down_since: float | None = None
_last: dict[str, Any] | None = None


def reset_for_tests() -> None:
    global _down_since, _last
    _down_since = _last = None
    _warned.clear()


def task_name() -> str | None:
    """The task to run, or None: unset, not Windows, or a feed on another machine (logged once)."""
    name = (os.environ.get(FOLLOWED_FEED_TASK_ENV) or "").strip()
    base = config.feed_url()
    if not name or base is None:
        return None
    if sys.platform != "win32":
        _warn_once("platform", "%s is set but Nova starts a scheduled task only on Windows", FOLLOWED_FEED_TASK_ENV)
        return None
    if (urlsplit(base).hostname or "").lower() not in FOLLOWED_KEEPER_HOSTS:
        _warn_once("host", "%s is set but the feed is not on this machine; Nova starts nothing", FOLLOWED_FEED_TASK_ENV)
        return None
    return name


def in_capture_hours(now: float) -> bool:
    """A weekday from ``FOLLOWED_KEEPER_CAPTURE_FROM_ET`` to ``FOLLOWED_KEEPER_CAPTURE_UNTIL_ET`` ET."""
    et = datetime.fromtimestamp(now, ET)
    return et.weekday() < 5 and FOLLOWED_KEEPER_CAPTURE_FROM_ET <= et.strftime("%H:%M") < FOLLOWED_KEEPER_CAPTURE_UNTIL_ET


def heartbeat(status: dict[str, Any] | None) -> float | None:
    """The capture's last sign of life: the newer of its last read and its last stated problem."""
    if status is None:
        return None
    times = [t for t in (status.get("updated_at"), status.get("problem_at")) if t is not None]
    return max(times) if times else None


def decide(now: float, *, down_since: float | None, beat: float | None, capture_hours: bool,
           last_run_at: float | None) -> str | None:
    """Why to run the task now, or None. ``down_since``: when the current run of unanswered asks began (None when the
    feed answered); ``beat``: the capture's last sign of life (``heartbeat``)."""
    if last_run_at is not None and now - last_run_at < FOLLOWED_KEEPER_COOLDOWN_SEC:
        return None
    if down_since is not None:
        down = now - down_since
        return f"the feed did not answer for {down:.0f} s" if down >= FOLLOWED_KEEPER_DOWN_SEC else None
    if not capture_hours:
        return None
    if beat is None:
        return "the capture has not reported yet"
    quiet = now - beat
    return f"the capture has read nothing for {quiet / 60:.0f} min" if quiet >= FOLLOWED_KEEPER_STALE_SEC else None


def run_task(name: str) -> str | None:
    """Ask Task Scheduler to run ``name``; None when it accepted, else its words."""
    try:
        done = subprocess.run(["schtasks", "/Run", "/TN", name], capture_output=True, text=True, check=False,
                              timeout=FOLLOWED_KEEPER_RUN_TIMEOUT_SEC,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as exc:
        return f"schtasks did not run: {type(exc).__name__}"
    if done.returncode == 0:
        return None
    said = (done.stderr or done.stdout or "").strip().splitlines()
    return said[0] if said else f"schtasks exited {done.returncode}"


def tick(now: float) -> None:
    """Blocking (call from a worker thread): ask the feed once, run the task if the rule says so."""
    global _down_since, _last
    name, base = task_name(), config.feed_url()
    if name is None or base is None:
        return
    beat = None
    try:
        day = feed.fetch_day(base, None)
        _down_since = None
        beat = heartbeat(day["status"])
    except feed.FeedError as exc:
        if exc.state != "unreachable":
            return  # an answer Nova cannot read is not a stopped feed
        if _down_since is None:
            _down_since = now
    why = decide(now, down_since=_down_since, beat=beat, capture_hours=in_capture_hours(now),
                 last_run_at=_last["at"] if _last else None)
    if why is None:
        return
    logger.warning("followed traders: running the task %r because %s", name, why)
    error = run_task(name)
    if error:
        logger.error("followed traders: the task %r did not run: %s", name, error)
    _last = {"at": round(now, 3), "why": why, "ok": error is None, "error": error}


async def run() -> None:
    """The backend's loop: one ask every ``FOLLOWED_KEEPER_TICK_SEC``, page open or not."""
    while True:
        try:
            await asyncio.to_thread(tick, time.time())
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- the keeper must outlive any one bad ask
            logger.exception("followed traders keeper")
        await asyncio.sleep(FOLLOWED_KEEPER_TICK_SEC)


def view(now: float | None = None) -> dict[str, Any] | None:
    """``/day``'s ``keeper``: the task, its newest run, and the earliest it can run again; None when none is set."""
    name = task_name()
    if name is None:
        return None
    now = time.time() if now is None else now
    next_at = _last["at"] + FOLLOWED_KEEPER_COOLDOWN_SEC if _last else None
    return {"task": name, "last": dict(_last) if _last else None,
            "next_at": next_at if next_at is not None and next_at > now else None}


def _warn_once(key: str, msg: str, *args: Any) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning(msg, *args)
