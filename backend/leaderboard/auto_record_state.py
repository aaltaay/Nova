"""What auto-record remembers across a restart: its own recordings and the operator's stops (#698).

``leaderboard.auto_record`` keeps who holds an auto line in process memory. The 2026-10-02
07:53:40 ET restart lost it: the keepalive resumed SSM (near), SORA (armed) and TNMG (leader) as
if the operator had recorded them, auto-record started three leaders on top, and SSM came back as
a recording auto-record could never give back to the operator. A symbol the operator stopped was
forgotten the same way, so auto-record could take it again that day.

The file ``auto-record.json`` in the operator cache (AGENTS.md section 3, auto-record):
``{schema_version: 1, date: "YYYY-MM-DD" (Eastern), held: {SYMBOL: {since, why}}, declined: [SYMBOL],
operator: [SYMBOL]}`` -- ``since`` epoch seconds auto-record started it, ``why`` the reason it was
last wanted (``trade | near | armed | leader``); ``operator`` the recordings the operator started
(or took over) today, absent in files written before it (none). Owner: this module. Invalidation: rewritten on every change;
another day reads as empty, so each session day starts fresh. An unknown version or an unreadable
file reads as empty and is logged -- what auto-record knew before this file existed, never a guess.

After a restart, a recording the file names that the keepalive resumed is auto-record's again
(``restore``); one a resume is still bringing back waits; the rest are forgotten.

**Unknown is never the operator's** (2026-10-02). A recording a restart brought back that the
file does not name as the operator's is auto-record's too, so it gives way to the operator's
Level 2. At 10:36 the backend came up on the first build with this file; the process before it
never wrote one, so SDEV, SSM and CELU -- all three auto-record's -- read as the operator's own,
were never given back, and AZTA's Level 2 read "Symbol cap reached" for over an hour.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

AUTO_RECORD_STATE_FILE = "auto-record.json"
AUTO_RECORD_STATE_SCHEMA_VERSION = 1

_restored: dict[str, dict[str, Any]] = {}  # what it held before the restart, until adopted or gone
_restored_day: str | None = None


def reset_for_tests() -> None:
    global _restored_day
    _restored.clear()
    _restored_day = None


def path() -> Path:
    from paths import cache_dir

    return cache_dir() / AUTO_RECORD_STATE_FILE


def today(ts: float | None = None) -> str:
    return datetime.fromtimestamp(time.time() if ts is None else ts, ET).date().isoformat()


def load(day: str, *, at: Path | None = None) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    """``(held, declined, operator)`` the file names for ``day``; empty for another day or a file it cannot read."""
    p = at or path()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, [], []
    except (OSError, ValueError):
        logger.warning("AUTO-RECORD: %s is unreadable -- starting with no recordings of its own", p, exc_info=True)
        return {}, [], []
    if not isinstance(doc, dict) or doc.get("schema_version") != AUTO_RECORD_STATE_SCHEMA_VERSION:
        version = doc.get("schema_version") if isinstance(doc, dict) else "?"
        logger.warning("AUTO-RECORD: %s has schema_version %s; this build reads %s -- ignored",
                       p, version, AUTO_RECORD_STATE_SCHEMA_VERSION)
        return {}, [], []
    if doc.get("date") != day:
        return {}, [], []
    held: dict[str, dict[str, Any]] = {}
    for sym, row in (doc.get("held") or {}).items():
        if isinstance(sym, str) and sym.strip() and isinstance(row, dict):
            since = row.get("since")
            held[sym.strip().upper()] = {
                "since": float(since) if isinstance(since, (int, float)) else None,
                "why": row.get("why") if isinstance(row.get("why"), str) else None,
            }
    declined = [str(s).strip().upper() for s in doc.get("declined") or [] if str(s).strip()]
    operator = [str(s).strip().upper() for s in doc.get("operator") or [] if str(s).strip()]
    return held, declined, operator


def write(day: str, held: dict[str, dict[str, Any]], declined: Iterable[str], operator: Iterable[str] = (), *,
          at: Path | None = None) -> None:
    """Rewrite the file; a failure is logged and costs only what a restart would remember."""
    from capture.manifest_io import write_json_atomic

    doc = {
        "schema_version": AUTO_RECORD_STATE_SCHEMA_VERSION,
        "date": day,
        "held": {sym: {"since": row.get("since"), "why": row.get("why")} for sym, row in sorted(held.items())},
        "declined": sorted(set(declined)),
        "operator": sorted(set(operator)),
    }
    try:
        write_json_atomic(at or path(), doc)
    except OSError:
        logger.exception("AUTO-RECORD: could not write %s -- a restart would forget its recordings", at or path())


def _rows(auto: dict[str, float], wanted_as: dict[str, str], declined: dict[str, str], day: str):
    held = {s: {"since": since, "why": wanted_as.get(s)} for s, since in auto.items()}
    return held, [s for s, d in declined.items() if d == day]


async def save(auto: dict[str, float], wanted_as: dict[str, str], declined: dict[str, str],
               operator: dict[str, str] | None = None) -> None:
    """auto-record's maps as they stand, written off the loop."""
    day = today()
    held, declined_today = _rows(auto, wanted_as, declined, day)
    mine = [s for s, d in (operator or {}).items() if d == day]
    await asyncio.to_thread(write, day, held, declined_today, mine)


def save_soon(auto: dict[str, float], wanted_as: dict[str, str], declined: dict[str, str],
              operator: dict[str, str] | None = None) -> asyncio.Task | None:
    """From a sync caller (the Record route): saved on the running loop; with none, at the next change."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # maintainer: allow-swallow no loop (a test): the next start or stop writes it
        return None
    return loop.create_task(save(dict(auto), dict(wanted_as), dict(declined), dict(operator or {})))


def forget(symbol: str) -> None:
    """The operator took or stopped it: it is not auto-record's to adopt."""
    _restored.pop(symbol, None)


def adoptable(restored: dict[str, dict[str, Any]], *, recording: Iterable[str], resuming: Iterable[str],
              owned: Iterable[str], declined: Iterable[str]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """``(adopt, forget)`` among the recordings auto-record held before the restart.

    One recording again (the keepalive resumed it) is auto-record's to adopt; one a resume is still
    bringing back waits; one already owned, declined by the operator, or no longer coming back is
    forgotten.
    """
    recording, resuming = set(recording), set(resuming)
    owned, declined = set(owned), set(declined)
    adopt: dict[str, dict[str, Any]] = {}
    gone: list[str] = []
    for sym, row in restored.items():
        if sym in owned or sym in declined:
            gone.append(sym)
        elif sym in recording:
            adopt[sym] = row
        elif sym not in resuming:
            gone.append(sym)
    return adopt, gone


async def restore(ts: float, *, auto: dict[str, float], wanted_as: dict[str, str], declined: dict[str, str],
                  recording: Iterable[str], resuming: Iterable[str], operator: dict[str, str] | None = None,
                  restarted: Iterable[str] = ()) -> list[str]:
    """Read the file once a day, then adopt into ``auto`` / ``wanted_as`` what came back; the adopted.

    ``restarted``: recordings the keepalive brought back from the process before this one
    (``keepalive.restart_symbols``) -- one the file names neither as auto-record's nor as the
    operator's is auto-record's too: an unknown starter never keeps a line from the operator.
    """
    global _restored_day
    operator = operator if operator is not None else {}
    day = today(ts)
    if _restored_day != day:
        held, declined_names, operator_names = await asyncio.to_thread(load, day)
        _restored.clear()
        _restored.update(held)
        _restored_day = day
        for sym in declined_names:
            declined.setdefault(sym, day)
        for sym in operator_names:
            operator.setdefault(sym, day)
    mine = {s for s, d in operator.items() if d == day}
    for sym in restarted:
        if sym not in _restored and sym not in auto and sym not in mine:
            _restored[sym] = {"since": None, "why": None, "unknown": True}
    if not _restored:
        return []
    adopt, gone = adoptable(_restored, recording=recording, resuming=resuming, owned=set(auto) | mine,
                            declined=[s for s, d in declined.items() if d == day])
    for sym in gone:
        _restored.pop(sym, None)
    for sym, row in adopt.items():
        _restored.pop(sym, None)
        auto[sym] = row.get("since") or ts
        if row.get("why"):
            wanted_as[sym] = row["why"]
        if row.get("unknown"):
            logger.warning("AUTO-RECORD: %s came back after the restart with no owner on file -- auto-record's, "
                           "so it gives way to the operator's Level 2", sym)
        else:
            logger.info("AUTO-RECORD: %s resumed after the restart is its own again (%s)", sym, row.get("why"))
    if adopt:
        await save(auto, wanted_as, declined, operator)
    return sorted(adopt)
