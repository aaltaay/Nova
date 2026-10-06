"""Pure IBC records and timestamp evidence for the #14 verifier (#742).

The operator's diagnostic parser keeps its own contract. This parser owns the
stricter proof rule: rejected timestamps cannot become observed weekday logins.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime

_STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}:\d+ IBC: ")
_BANNER_RE = re.compile(
    r"Starting IBC version \S+ on .*?(\d{1,2})/(\d{1,2})/(\d{4}) at\s+"
    r"(\d{1,2}):(\d{2}):(\d{2})(?:\.\d+)?")


@dataclass(frozen=True)
class LoginRecord:
    ts: float | None
    full_auth: bool


@dataclass(frozen=True)
class IbcEvidence:
    logins: tuple[LoginRecord, ...]
    stamps: tuple[float, ...]
    problems: tuple[str, ...]


def _local(text: str) -> float | None:
    try:
        return time.mktime(datetime.strptime(text, "%Y-%m-%d %H:%M:%S").timetuple())
    except (ValueError, OverflowError, OSError):
        return None


def _banner_ts(line: str) -> float | None:
    match = _BANNER_RE.fullmatch(line)
    if match is None:
        return None
    month, day, year, hour, minute, second = map(int, match.groups())
    return _local(f"{year:04}-{month:02}-{day:02} {hour:02}:{minute:02}:{second:02}")


def parse_ibc_evidence(text: str) -> IbcEvidence:
    """Parse each auth record once, together with its retained evidence limits.

    A banner belongs to its first auth record on that startup date. A following
    dated IBC line must not predate that banner. Crossing another startup while
    awaiting that line rejects the record's timestamp instead of relabelling it.
    An unused banner still needs an outcome after its timestamp fallback expires.
    """
    logins, stamps, problems = [], [], []
    fresh_banner: float | None = None
    unmatched_banner = False
    pending: bool | None = None
    pending_banner: float | None = None

    def finish(ts: float | None, problem: str | None = None) -> None:
        nonlocal pending
        if pending is None:
            return
        logins.append(LoginRecord(ts=ts, full_auth=pending))
        if ts is None:
            problems.append(problem or "an authentication record has no fresh banner or following dated IBC line")
        pending = None

    for raw in text.splitlines():
        line = raw.strip()
        low = line.lower()
        if low.startswith("starting ibc version"):
            if unmatched_banner:
                problems.append("an IBC startup has no authentication outcome")
            finish(None, "an undated authentication record crosses another IBC startup")
            fresh_banner = _banner_ts(line)
            unmatched_banner = fresh_banner is not None
            if fresh_banner is None:
                problems.append("a malformed IBC startup banner cannot establish when authentication occurred")
            continue
        if low.startswith(("autorestart file not found", "autorestart file found")):
            finish(pending_banner)
            pending = low.startswith("autorestart file not found")
            pending_banner, fresh_banner = fresh_banner, None
            unmatched_banner = False
            continue
        if _STAMP_RE.match(line):
            ts = _local(line[:19])
            if ts is None:
                problems.append("a dated log line has an unreadable timestamp")
                continue
            stamps.append(ts)
            if pending is not None:
                if pending_banner is not None and ts < pending_banner:
                    finish(None, "a dated authentication line predates its IBC startup banner")
                else:
                    finish(ts)
            elif fresh_banner is not None and datetime.fromtimestamp(ts).date() != datetime.fromtimestamp(fresh_banner).date():
                fresh_banner = None
    finish(pending_banner)
    if unmatched_banner:
        problems.append("an IBC startup has no authentication outcome")
    stamps.extend(login.ts for login in logins if login.ts is not None)
    return IbcEvidence(tuple(logins), tuple(stamps), tuple(sorted(set(problems))))
