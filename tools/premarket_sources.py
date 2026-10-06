"""Availability and dated history of the read-only premarket proof sources (#742).

Owner: premarket_verify.py. A successful empty read differs from missing evidence;
retained observation dates describe the history we have, never continuous monitoring.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReadResult:
    status: str
    read_at: float
    texts: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()

    def summary(self, stamps: list[float]) -> dict[str, Any]:
        return {
            "status": self.status, "read_at": self.read_at,
            "first_ts": min(stamps) if stamps else None,
            "last_ts": max(stamps) if stamps else None,
            "dates": sorted({time.strftime("%Y-%m-%d", time.localtime(ts)) for ts in stamps}),
            "problems": list(self.problems),
        }


def read_log(path: Path, now: float) -> ReadResult:
    """Read one log without replacing failed reads or invalid bytes with empty text."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        return ReadResult("missing", now, problems=(f"{path.name}: {exc}",))
    except (OSError, UnicodeError) as exc:
        return ReadResult("unreadable", now, problems=(f"{path.name}: {exc}",))
    return ReadResult("readable", now, texts=(text,))


def read_ibc_logs(directory: Path, now: float) -> ReadResult:
    """Read every matching file. A failed file keeps the whole source partial.

    iterdir is intentional: glob may suppress directory-listing errors.
    """
    try:
        files = sorted(path for path in directory.iterdir() if path.match("IBC-*.txt"))
    except FileNotFoundError as exc:
        return ReadResult("missing", now, problems=(f"IBC directory: {exc}",))
    except OSError as exc:
        return ReadResult("unreadable", now, problems=(f"IBC directory: {exc}",))
    if not files:
        return ReadResult("missing", now, problems=("no IBC-*.txt files in the directory",))
    texts, problems, statuses = [], [], []
    for path in files:
        result = read_log(path, now)
        texts.extend(result.texts)
        problems.extend(result.problems)
        statuses.append(result.status)
    status = ("readable" if not problems else "partial" if texts else
              "missing" if all(status == "missing" for status in statuses) else "unreadable")
    return ReadResult(status, now, texts=tuple(texts), problems=tuple(problems))


def windows_supported() -> bool:
    return sys.platform == "win32"


def restart_source(restarts: list | None, days: int, now: float, supported: bool) -> dict[str, Any]:
    status = "unsupported" if not supported else "unreadable" if restarts is None else "readable"
    problem = ("Windows restart evidence is unsupported on this platform" if not supported else
               "the Windows event log could not be read" if restarts is None else None)
    return {
        **ReadResult(status, now, problems=(problem,) if problem else ()).summary([]),
        "queried_since": now - (days + 1) * 86400 if supported else None,
    }


def quiet_proof(sources: dict[str, dict], *, restarts: list | None,
                days: int, now: float, minimum_days: int) -> dict[str, Any]:
    """Whether source/window facts support absence; event counts cannot prove availability.

    A dated line before the window alone is inadequate. Both retained login sources
    must also name every completed observation date, and be successfully read now.
    These bounds describe the retained observations, not continuous collection.
    """
    since = now - days * 86400
    problems: list[str] = []
    if days < minimum_days:
        problems.append(f"#14 needs at least {minimum_days} days; the requested window is {days}")
    for name in ("daily_start", "ibc"):
        source = sources.get(name)
        if source is None:
            problems.append(f"{name}: source availability and dated observations are unknown")
            continue
        problems.extend(f"{name}: {problem}" for problem in source.get("problems", []))
        if source.get("status") != "readable":
            problems.append(f"{name}: source is {source.get('status', 'unknown')}")
        first = source.get("first_ts")
        if first is None:
            problems.append(f"{name}: no dated observations establish the requested window")
        elif first > since:
            problems.append(f"{name}: retained observations do not reach the requested window start")
        last = source.get("last_ts")
        if last is not None and last > now:
            problems.append(f"{name}: a retained timestamp is in the future")
        if source.get("read_at", 0) < now:
            problems.append(f"{name}: source has not been read at the report time")
        dates = set(source.get("dates", []))
        day, today = datetime.fromtimestamp(since).date(), datetime.fromtimestamp(now).date()
        missing = []
        while day < today:
            if day.isoformat() not in dates:
                missing.append(day.isoformat())
            day += timedelta(days=1)
        if missing:
            problems.append(f"{name}: no retained dated observations on {', '.join(missing)}")
    restart = sources.get("windows_restarts") or {}
    problems.extend(f"windows_restarts: {problem}" for problem in restart.get("problems", []))
    if restarts is None and restart.get("status") == "readable":
        problems.append("windows_restarts: the query result is unavailable")
    elif restart.get("status") != "readable":
        problems.append(f"windows_restarts: restart proof is {restart.get('status', 'unknown')}")
    queried_since = restart.get("queried_since")
    if queried_since is None or queried_since > since or restart.get("read_at", 0) < now:
        problems.append("windows_restarts: query does not establish the requested window")
    return {"complete": not problems, "requested_from": since, "requested_through": now,
            "problems": problems}
