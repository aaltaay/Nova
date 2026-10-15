"""The low-memory notice: the strip under the desk's header while the PC runs short (operator ask 2026-10-15).

At 08:45 ET a one-off analysis script grew past 175 GB on the 96 GB desk PC. Free RAM went from 48 GB to
0.1 GB in two minutes, Windows paged, and at 09:02 the TraderTV LIVE page went blank. The memory watch read it
every minute and the ``pc_memory`` row said "nearly out" from 08:47, inside a checklist nobody had open. The
operator's picks: the row's own line (``PERF_MEMORY_PRESSURE_PCT``, under about 10 GB free on that PC) and a
strip under the header, during the trading session, naming the process holding the most -- and warn only.

``notice`` is the rule and the words (pure); ``view`` is ``GET /api/perf/memory-notice``. The program is named
only here, for the desk: never in the API log (an issue dump prints it) nor in a diagnostics row's detail. Nothing
here, or anywhere in Nova, stops, pauses or slows a program because of memory. Schema:
architecture/schema/desk-ops.md ("The low-memory notice").
"""
from __future__ import annotations

import time
from typing import Any

from constants_perf import (
    PERF_MEMORY_CRITICAL_PCT,
    PERF_MEMORY_GROUP_OUTWEIGHS,
    PERF_MEMORY_NOTICE_SCHEMA_VERSION,
    PERF_MEMORY_PRESSURE_PCT,
    PERF_MEMORY_STALE_SEC,
)
from perf.memory_watch import PART_WORDS, gb, pressure_pct

ONLY_WARNS = "Nova only warns: it never stops a program. Task Manager > Details, by PID."


def run_words(sec: float) -> str:
    """``under a minute``, ``12 min``, ``3 h 5 min``, ``2 d 4 h``."""
    minutes = max(0, int(sec)) // 60
    if minutes < 1:
        return "under a minute"
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    days, hours = divmod(hours, 24)
    return f"{days} d {hours} h" if hours else f"{days} d"


def biggest_view(read: dict[str, Any], now: float) -> dict[str, Any] | None:
    """The reading's biggest process, with how long it has run at ``now`` (None when Windows did not say)."""
    biggest = read.get("biggest")
    if not biggest:
        return None
    born = biggest.get("started_at")
    return {**biggest, "run_sec": round(max(0.0, now - born)) if born is not None else None}


def outweighing_group(read: dict[str, Any], biggest: dict[str, Any] | None) -> dict[str, Any] | None:
    """Another program whose processes together hold PERF_MEMORY_GROUP_OUTWEIGHS times the biggest one.

    The 32 GB desk PC of 2026-10-12 to 14 was full of one program's dozens of 1-2 GB processes: its biggest
    single process said nothing about where the memory went."""
    if biggest is None:
        return None
    for group in read.get("others") or []:          # biggest total first
        if group["count"] > 1 and group["private_mb"] >= PERF_MEMORY_GROUP_OUTWEIGHS * max(1, biggest["private_mb"]):
            return {"name": group["name"], "count": group["count"], "private_mb": group["private_mb"]}
    return None


def biggest_words(biggest: dict[str, Any] | None, group: dict[str, Any] | None) -> str:
    """``Biggest: python3.13.exe, PID 63476, holds 118.6 GB, running 3 min.`` and the group's sentence."""
    if biggest is None:
        return "Biggest: no process could be read."
    who = biggest["name"]
    if biggest.get("role"):
        who = f"Nova's {PART_WORDS.get(biggest['role'], biggest['role'])} ({who})"
    ran = biggest.get("run_sec")
    age = f"running {run_words(ran)}" if ran is not None else "start time unknown"
    words = f"Biggest: {who}, PID {biggest['pid']}, holds {gb(biggest['private_mb'])}, {age}."
    if group is not None:
        together = f"{group['count']} {group['name']} processes"
        if group["name"].lower() == biggest["name"].lower() and not biggest.get("role"):
            words += f" It is one of {together}, {gb(group['private_mb'])} together."
        else:
            words += f" {together} hold {gb(group['private_mb'])} together."
    return words


def _text(level: str, pc: dict[str, int], now: float, last_low_at: float) -> str:
    free = f"{gb(pc['ram_free_mb'])} of {round(pc['ram_total_mb'] / 1024)} GB free"
    committed = f"{round(pc['commit_used_mb'] / 1024)} of {round(pc['commit_limit_mb'] / 1024)} GB committed"
    if level == "nearly_out":
        return f"PC memory nearly out: {free}, {committed}."
    if level == "low":
        return f"PC memory low: {free}." if pc["load_pct"] >= PERF_MEMORY_PRESSURE_PCT else f"PC memory low: {committed}."
    ago = now - last_low_at
    when = "under a minute ago" if ago < 60 else f"{int(ago // 60)} min ago"
    return f"PC memory was low {when}: {free} now."


def notice(*, status: dict[str, Any], now: float, in_session: bool) -> dict[str, Any] | None:
    """The notice the desk shows now, or None: outside the session, the watch off or not read yet, a stale
    reading, no episode open, or a reading without the PC's numbers."""
    read, episode = status.get("last"), status.get("episode")
    if not in_session or not status.get("available") or read is None or episode is None:
        return None
    pc = read.get("pc")
    if not pc or now - float(read["ts"]) > PERF_MEMORY_STALE_SEC:
        return None
    pct = pressure_pct(pc) or 0
    level = "nearly_out" if pct >= PERF_MEMORY_CRITICAL_PCT else "low" if pct >= PERF_MEMORY_PRESSURE_PCT else "easing"
    biggest = biggest_view(read, now)
    group = outweighing_group(read, biggest)
    return {
        "level": level,
        "key": f"{episode['since']:.0f}|{episode['pid']}",
        "since": episode["since"],
        "ts": read["ts"],
        "text": _text(level, pc, now, float(episode["last_low_at"])),
        "hint": f"{biggest_words(biggest, group)} {ONLY_WARNS}",
        "pc": dict(pc),
        "biggest": biggest,
        "group": group,
    }


def view(now: float | None = None) -> dict[str, Any]:
    """``GET /api/perf/memory-notice``: whether Nova's trading session is on, and the notice."""
    from market import in_trading_session
    from perf import memory_watch

    t = time.time() if now is None else now
    in_session = in_trading_session(t)
    return {
        "schema_version": PERF_MEMORY_NOTICE_SCHEMA_VERSION,
        "generated_at": round(t, 3),
        "in_session": in_session,
        "notice": notice(status=memory_watch.status(), now=t, in_session=in_session),
    }
