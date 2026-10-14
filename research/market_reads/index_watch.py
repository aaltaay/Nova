"""The bulk index build's watchdog: free memory, failures in a row, the run's status file and the operator's alert.

2026-10-13: a 20-hour run failed 191 day files (`zran_init returned error`, every quotes day for its last two hours)
while its workers grew until the PC ran short of memory, and the only trace was a warning line in a log nobody was
reading. Now every failure is counted on every progress line, the first one and any halt raise a Windows
notification, five in a row halt the run (``<root>/sim/index/STOP`` with the reason), a build waits for free memory
before it starts and halts the run when none comes, and ``index-status.json`` says what the run is doing -- or that
its process is gone -- to ``tools/market_data.py status`` and the downloads page.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

STATUS_FILE = "index-status.json"
SCHEMA_VERSION = 1
FAILURE_STREAK_HALT = 5          # failed builds in a row that halt the run: one bad file is a file, five are the run
RAM_FLOOR_GB = 3.0               # a build starts only with this much physical memory free
RAM_WAIT_SEC = 600.0             # ... and halts the run when none frees up for this long
RAM_POLL_SEC = 5.0
HEARTBEAT_SEC = 30.0             # the status file is rewritten at least this often while the run lives
STALE_SEC = 180.0                # a "running" status older than this, or whose process is gone, is a run that died
FAILURES_KEPT = 50               # the status file names the latest failures; the count is always whole
ALERTS_ENV = "NOVA_INDEX_ALERTS"  # "0": no Windows notification (tests, CI)
CREATE_NO_WINDOW = 0x08000000    # the notification's PowerShell draws no console window
# Windows PowerShell's own app id: a notification needs a registered sender, and this one is on every Windows 10/11.
TOAST_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
TOAST_SCRIPT = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]"
    " > $null; $t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
    "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); $x = $t.GetElementsByTagName('text');"
    " $x.Item(0).AppendChild($t.CreateTextNode($env:NOVA_TOAST_TITLE)) > $null;"
    " $x.Item(1).AppendChild($t.CreateTextNode($env:NOVA_TOAST_BODY)) > $null;"
    " [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:NOVA_TOAST_APP).Show("
    "[Windows.UI.Notifications.ToastNotification]::new($t))")

log = logging.getLogger("market_reads")


class _MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def free_ram() -> int | None:
    """Free physical memory in bytes; ``None`` when this OS will not say (then nothing waits on it)."""
    if os.name == "nt":
        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(_MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullAvailPhys)
        return None
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        return None
    return None


def wait_for_ram(floor_gb: float, wait_sec: float, stop_file: Path) -> bool:
    """True once ``floor_gb`` of memory is free (at once when the OS will not say); False after ``wait_sec`` without
    it. A STOP that appears while waiting ends the wait too (True: the caller's own STOP check returns)."""
    deadline = time.monotonic() + wait_sec
    while True:
        free = free_ram()
        if free is None or free >= floor_gb * 1e9 or stop_file.exists():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(RAM_POLL_SEC)


def alert(title: str, body: str) -> None:
    """Tell the operator now: a Windows notification (and always the log). Never raises; nothing but Windows shows it."""
    log.warning("index: ALERT %s -- %s", title, body)
    if os.name != "nt" or os.environ.get(ALERTS_ENV) == "0":
        return
    env = {**os.environ, "NOVA_TOAST_TITLE": title, "NOVA_TOAST_BODY": body, "NOVA_TOAST_APP": TOAST_APP_ID}
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", TOAST_SCRIPT], env=env,
                         creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        log.warning("index: the notification could not be shown (%s); the log and %s still say it", exc, STATUS_FILE)


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        process_query_limited, still_active = 0x1000, 259
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_status(folder: Path) -> dict[str, Any] | None:
    """The last run's status file, with ``state`` "died" for a run whose process is gone or that stopped writing.
    ``None`` when no run has written one; an unknown ``schema_version`` is said, never read as this one."""
    path = folder / STATUS_FILE
    try:
        out = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "error": f"{type(exc).__name__}: {exc}", "path": str(path)}
    if out.get("schema_version") != SCHEMA_VERSION:
        return {"state": "unreadable", "error": f"schema_version {out.get('schema_version')!r}", "path": str(path)}
    if out.get("state") == "running":
        age = time.time() - float(out.get("updated", 0))
        if age > STALE_SEC or not _pid_alive(int(out.get("pid", 0))):
            out["state"] = "died"
            out["reason"] = (f"process {out.get('pid')} is gone or stopped writing {age / 60:.0f} min ago, with no "
                             "stop or finish recorded (killed, crashed, or the PC restarted)")
    return out


class Watch:
    """One run's status, written atomically to ``<folder>/index-status.json`` on every event and every
    ``HEARTBEAT_SEC``, and the decision to halt: ``FAILURE_STREAK_HALT`` failures in a row, or no free memory."""

    def __init__(self, folder: Path, stop_file: Path, files: int, total_bytes: int, workers: int,
                 streak_halt: int = FAILURE_STREAK_HALT):
        self.path, self.stop_file, self.streak_halt = folder / STATUS_FILE, stop_file, streak_halt
        self.lock = threading.Lock()
        self.streak = 0
        self.data: dict[str, Any] = dict(
            schema_version=SCHEMA_VERSION, state="running", pid=os.getpid(), started=round(time.time(), 3),
            updated=0.0, files=files, total_gb=round(total_bytes / 1e9, 1), workers=workers, built=0, done_gb=0.0,
            mb_per_s=0.0, hours_left=None, failed=0, failures=[], reason=None, free_ram_gb=None, last=None)
        self.halted = threading.Event()
        self._write()
        self._beat = threading.Thread(target=self._heartbeat, name="index-status", daemon=True)
        self._beat.start()

    def _heartbeat(self) -> None:
        while self.data["state"] == "running":
            time.sleep(HEARTBEAT_SEC)
            if self.data["state"] == "running":
                self._write()

    def _write(self) -> None:
        with self.lock:
            free = free_ram()
            self.data["free_ram_gb"] = None if free is None else round(free / 1e9, 1)
            self.data["updated"] = round(time.time(), 3)
            part = self.path.with_name(f"{self.path.name}.{os.getpid()}.part")
            try:
                part.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
                os.replace(part, self.path)
            except OSError as exc:
                log.warning("index: %s could not be written (%s)", self.path, exc)

    def built(self, path: str, done_bytes: int, rate: float, left_sec: float) -> None:
        self.streak = 0
        self.data.update(built=self.data["built"] + 1, done_gb=round(done_bytes / 1e9, 1),
                         mb_per_s=round(rate / 1e6), hours_left=round(left_sec / 3600, 1), last=path)
        self._write()

    def failed(self, what: str) -> None:
        """A build failed: counted, named, the first one alerted, and ``streak_halt`` in a row halt the run."""
        self.streak += 1
        self.data["failed"] += 1
        self.data["failures"] = [*self.data["failures"], {"at": round(time.time(), 3), "what": what}][-FAILURES_KEPT:]
        if self.data["failed"] == 1 and self.streak < self.streak_halt:
            alert("Nova index build: a day file failed", f"{what[:180]} -- the run goes on; it stops after "
                  f"{self.streak_halt} failures in a row.")
        if self.streak >= self.streak_halt:
            self.halt(f"{self.streak} builds failed in a row; the last: {what}")
        else:
            self._write()

    def halt(self, reason: str) -> None:
        """Stop the run after the files in progress, say why in STOP and the status file, and alert -- once."""
        if self.halted.is_set():
            return
        self.halted.set()
        self.data["reason"] = reason
        try:
            self.stop_file.write_text(f"halted by the run itself: {reason}\n", encoding="utf-8")
        except OSError as exc:
            log.warning("index: could not write %s (%s); the run goes on", self.stop_file, exc)
        log.warning("index: HALT %s", reason)
        alert("Nova index build halted", f"{reason[:200]} -- {self.data['failed']} failed so far; see "
              f"{self.path.parent}")
        self._write()

    def finish(self, state: str, files_left: int) -> None:
        """``finished`` / ``stopped`` / ``halted``: the run's last word, and a notification when it did not finish."""
        self.data.update(state=state, files_left=files_left, ended=round(time.time(), 3))
        self._write()
        if state == "finished":
            alert("Nova index build finished", f"{self.data['built']} built, {self.data['failed']} failed.")
