"""When did this PC restart, who restarted it, and when did anyone sign in?

Owner: this module. Read-only -- it queries the Windows System event log with
``wevtutil`` and never writes anything.

Why (#14, 2026-09-23): IB Gateway's saved login survives only its own 11:45 PM
restart. A PC restart ends it, so the next start needs the operator's phone.
That morning Windows Update restarted the desk at 02:29 ET and Windows sat at
the sign-in screen until 09:22, so neither the 03:40 start nor the 03:55 check
ran -- and nothing on the desk said why. These facts let Nova say so.

Events read (System log):
- 12, provider Microsoft-Windows-Kernel-General -- the OS started (a boot);
- 1074, provider User32 -- a planned restart or shutdown: the process that
  asked (param1), the reason (param3, code param4), the Shutdown Type
  (param5: restart or power off) and on whose behalf (param7, and the
  event's Security UserID);
- 6008, provider EventLog -- the previous shutdown was unexpected;
- 7001, provider Microsoft-Windows-Winlogon -- a user signed in.

Invalidation: ``current_restart()`` is cached per boot, so the one
``wevtutil`` start (~0.1 s) happens at most once per boot per process.
"""
from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from constants_relogin import (
    RELOGIN_BOOT_MERGE_SEC,
    RELOGIN_POWER_BUTTON_REASON_CODE,
    RELOGIN_RESTART_CHAIN_SEC,
    RELOGIN_SHUTDOWN_TYPES,
    RELOGIN_SIGNIN_PROCESS,
    RELOGIN_START_MENU_PROCESSES,
    RELOGIN_SYSTEM_ACCOUNT,
    RELOGIN_SYSTEM_SID,
    RELOGIN_UNEXPECTED_AFTER_BOOT_SEC,
    RELOGIN_WEVTUTIL_MAX_EVENTS,
    RELOGIN_WEVTUTIL_TIMEOUT_SEC,
    RELOGIN_WINDOWS_UPDATE_PROCESSES,
)

logger = logging.getLogger(__name__)

_NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"
_BOOT = (12, "Microsoft-Windows-Kernel-General")
_PLANNED = (1074, "User32")
_UNEXPECTED = (6008, "EventLog")
_SIGNIN = (7001, "Microsoft-Windows-Winlogon")


@dataclass(frozen=True)
class Restart:
    """One restart of the PC, as the event log records it.

    ``cause`` is ``windows_update`` | ``start_menu`` | ``power_button`` (the
    PC's power button) | ``app`` (another program asked) | ``unexpected``
    (power loss, crash, forced power-off) | ``unknown`` (a boot with no record
    of why). ``shutdown_type`` is the 1074's ``restart`` | ``power_off`` |
    ``shutdown``, ``None`` without one (or in a word Nova cannot read).
    """

    boot_ts: float
    cause: str
    label: str
    initiated_ts: float | None = None
    process: str | None = None
    windows_reason: str | None = None
    first_signin_ts: float | None = None
    reason_code: str | None = None
    shutdown_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_events_xml(text: str) -> list[dict[str, Any]] | None:
    """``wevtutil qe /f:xml`` prints bare ``<Event>`` elements; wrap and read
    them into ``{id, provider, ts, sid, data}`` rows (``sid`` the event's
    Security UserID or ``None``; ``data`` by ``Name``, else positional). Rows
    without a readable time are skipped; XML that does not parse is ``None``
    -- unknown, never 'no events'."""
    body = (text or "").strip()
    if not body:
        return []
    try:
        root = ET.fromstring(f"<Events>{body}</Events>")
    except ET.ParseError:
        logger.warning("windows_restarts: event XML unreadable", exc_info=True)
        return None
    rows: list[dict[str, Any]] = []
    for ev in root.iter(f"{_NS}Event"):
        system = ev.find(f"{_NS}System")
        if system is None:
            continue
        provider = system.find(f"{_NS}Provider")
        created = system.find(f"{_NS}TimeCreated")
        event_id = system.find(f"{_NS}EventID")
        security = system.find(f"{_NS}Security")
        ts = _parse_system_time(created.get("SystemTime") if created is not None else None)
        if ts is None or event_id is None or not (event_id.text or "").strip().isdigit():
            continue
        data: dict[str, str] = {}
        payload = ev.find(f"{_NS}EventData")
        if payload is not None:
            for i, item in enumerate(payload.findall(f"{_NS}Data")):
                data[item.get("Name") or str(i)] = (item.text or "").strip()
        rows.append({
            "id": int((event_id.text or "0").strip()),
            "provider": provider.get("Name") if provider is not None else "",
            "ts": ts,
            "sid": (security.get("UserID") or None) if security is not None else None,
            "data": data,
        })
    rows.sort(key=lambda r: r["ts"])
    return rows


def restarts_from_events(events: list[dict[str, Any]]) -> list[Restart]:
    """Pure: turn System events into restarts, oldest first.

    Boots closer than ``RELOGIN_BOOT_MERGE_SEC`` are one restart (Windows
    Update's second reboot) reported at the last boot with the first boot's
    cause -- the Gateway was down across both.
    """
    boots = [e["ts"] for e in events if (e["id"], e["provider"]) == _BOOT]
    planned = [e for e in events if (e["id"], e["provider"]) == _PLANNED]
    unexpected = [e["ts"] for e in events if (e["id"], e["provider"]) == _UNEXPECTED]
    signins = [e["ts"] for e in events if (e["id"], e["provider"]) == _SIGNIN]

    groups: list[list[float]] = []
    for boot in sorted(boots):
        if groups and boot - groups[-1][-1] <= RELOGIN_BOOT_MERGE_SEC:
            groups[-1].append(boot)
        else:
            groups.append([boot])

    restarts: list[Restart] = []
    for group in groups:
        first, last = group[0], group[-1]
        chain = [p for p in planned if first - RELOGIN_RESTART_CHAIN_SEC <= p["ts"] <= first]
        signin = next((s for s in signins if s >= last), None)
        if chain:
            starter = min(chain, key=lambda p: p["ts"])
            data = starter["data"]
            process = _process_name(data.get("param1", ""))
            shutdown_type = _shutdown_type(data.get("param5", ""))
            cause, label = _label(
                process,
                by_system=_on_behalf_of_system(starter.get("sid"), data.get("param7", "")),
                reason_code=_reason_code(data.get("param4", "")),
                shutdown_type=shutdown_type,
            )
            restarts.append(Restart(
                boot_ts=last,
                cause=cause,
                label=label,
                initiated_ts=starter["ts"],
                process=process or None,
                windows_reason=data.get("param3") or None,
                first_signin_ts=signin,
                reason_code=data.get("param4") or None,
                shutdown_type=shutdown_type,
            ))
        elif any(first <= u <= first + RELOGIN_UNEXPECTED_AFTER_BOOT_SEC for u in unexpected):
            restarts.append(Restart(
                boot_ts=last,
                cause="unexpected",
                label="an unexpected shutdown (power loss, a crash or a forced power-off)",
                first_signin_ts=signin,
            ))
        else:
            restarts.append(Restart(
                boot_ts=last,
                cause="unknown",
                label="a restart Windows did not record a reason for",
                first_signin_ts=signin,
            ))
    return restarts


def recent_restarts(days: float) -> list[Restart] | None:
    """Restarts in the last ``days``, oldest first. ``None`` when the event
    log cannot be read (not Windows, ``wevtutil`` failed) -- unknown, never
    an empty 'no restarts'."""
    text = _query_events(days)
    events = parse_events_xml(text) if text is not None else None
    if events is None:
        return None
    return restarts_from_events(events)


_cache: dict[str, Any] = {"boot_minute": None, "restart": None, "read": False}


def current_restart() -> Restart | None:
    """The restart that started this boot, or ``None`` when unknown.

    Cached per boot: the event log cannot change its answer until the next
    boot, so a diagnostics poll pays for ``wevtutil`` once.
    """
    boot = boot_ts()
    if boot is None:
        return None
    minute = int(boot // 60)
    if _cache["read"] and _cache["boot_minute"] == minute:
        return _cache["restart"]
    uptime_days = max(0.0, time.time() - boot) / 86400.0
    found = recent_restarts(uptime_days + 1.0)
    restart = None
    if found:
        # The last recorded boot is this one; the tick count and the event
        # time differ by the seconds Windows takes to start its event log.
        candidate = found[-1]
        if abs(candidate.boot_ts - boot) <= RELOGIN_BOOT_MERGE_SEC:
            restart = candidate
    # A restart nobody has signed in after yet can still gain its sign-in
    # time; keep asking until it has one.
    if found is not None and (restart is None or restart.first_signin_ts is not None):
        _cache.update(boot_minute=minute, restart=restart, read=True)
    return restart


def boot_ts() -> float | None:
    """Epoch seconds this Windows boot started (``GetTickCount64``, which
    counts sleep too, so a wake from sleep is not mistaken for a boot)."""
    if sys.platform != "win32":
        return None
    try:
        ticks = ctypes.windll.kernel32.GetTickCount64
        ticks.restype = ctypes.c_ulonglong
        return time.time() - float(ticks()) / 1000.0
    except Exception:
        logger.warning("windows_restarts: GetTickCount64 unavailable", exc_info=True)
        return None


def _query_events(days: float) -> str | None:
    if sys.platform != "win32":
        return None
    window_ms = int(max(days, 0.0) * 86400 * 1000)
    # Each id with its own provider: other providers write event 12 too (an
    # ASUS power tool wrote 818 in 8 days on the desk), and unfiltered they
    # filled the newest-first event cap, so a 'week' read held ~4 days.
    ids = " or ".join(
        f"(EventID={i} and Provider[@Name='{name}'])" for i, name in (_BOOT, _PLANNED, _UNEXPECTED, _SIGNIN)
    )
    query = f"*[System[({ids}) and TimeCreated[timediff(@SystemTime) <= {window_ms}]]]"
    try:
        completed = subprocess.run(
            ["wevtutil", "qe", "System", f"/q:{query}", f"/c:{RELOGIN_WEVTUTIL_MAX_EVENTS}", "/rd:true", "/f:xml"],
            capture_output=True,
            text=True,
            timeout=RELOGIN_WEVTUTIL_TIMEOUT_SEC,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        logger.warning("windows_restarts: wevtutil failed", exc_info=True)
        return None
    if completed.returncode != 0:
        logger.warning("windows_restarts: wevtutil exit %s: %s", completed.returncode, completed.stderr.strip()[:200])
        return None
    return completed.stdout


def _parse_system_time(raw: str | None) -> float | None:
    if not raw:
        return None
    text = raw.strip().rstrip("Z")
    if "." in text:
        head, frac = text.split(".", 1)
        text = f"{head}.{frac[:6]}"
    try:
        stamp = datetime.fromisoformat(text + "+00:00")
    except ValueError:
        return None
    return stamp.timestamp()


def _process_name(param1: str) -> str:
    """``C:\\WINDOWS\\uus\\AMD64\\MoUsoCoreWorker.exe (DESKTOP-X)`` -> basename."""
    path = param1.split(" (", 1)[0].strip()
    return path.replace("/", "\\").rsplit("\\", 1)[-1]


def _shutdown_type(param5: str) -> str | None:
    """``power off`` -> ``power_off``; a word Nova cannot read is ``None``."""
    return RELOGIN_SHUTDOWN_TYPES.get(param5.strip().lower())


def _reason_code(param4: str) -> int | None:
    try:
        return int(param4.strip(), 16)
    except ValueError:
        return None


def _on_behalf_of_system(sid: str | None, param7: str) -> bool:
    """No user asked: the event runs as LocalSystem (a SID every Windows
    language shares), or its text names ``NT AUTHORITY\\SYSTEM``."""
    return sid == RELOGIN_SYSTEM_SID or param7.strip().lower() == RELOGIN_SYSTEM_ACCOUNT


def _label(
    process: str,
    *,
    by_system: bool = False,
    reason_code: int | None = None,
    shutdown_type: str | None = None,
) -> tuple[str, str]:
    low = process.lower()
    if low in RELOGIN_WINDOWS_UPDATE_PROCESSES:
        return "windows_update", f"Windows Update ({process})"
    if low == RELOGIN_SIGNIN_PROCESS and by_system:
        if reason_code == RELOGIN_POWER_BUTTON_REASON_CODE and shutdown_type == "power_off":
            return "power_button", "the PC's power button"
        # Windows' sign-in process with no user named is never the Start
        # menu (that names its own process and the user); say only who asked.
        return "app", f"Windows' sign-in process ({process}), with no user named"
    if low in RELOGIN_START_MENU_PROCESSES:
        return "start_menu", "the Start menu"
    if not process:
        return "unknown", "a restart Windows did not record a reason for"
    return "app", f"{process}"
