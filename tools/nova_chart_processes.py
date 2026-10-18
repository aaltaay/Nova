"""Own a Windows Job tree from before real commands run until verified teardown.

Each command starts suspended, joins the Job, and only then runs, so it and everything it starts are in the Job
before it executes one instruction. This is explicit on purpose: under Microsoft Store (packaged) Python, a program
from outside the package that a packaged process starts -- node, the chart renderer -- is created outside the
creator's Jobs, so inheriting the Job is not enough (#1061). close() also walks each command's live descendants by
parent and creation time before it ends the Job, stops any that escaped it, and counts what is still alive after.
Unsupported platforms fail clearly rather than promise orphan cleanup they cannot verify.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import time

CREATE_SUSPENDED = 0x00000004
PROCESS_TERMINATE, PROCESS_SET_QUOTA, PROCESS_SUSPEND_RESUME = 0x0001, 0x0100, 0x0800
PROCESS_QUERY_LIMITED_INFORMATION, SYNCHRONIZE = 0x1000, 0x00100000
ERROR_INVALID_PARAMETER = 87  # OpenProcess on a PID that no longer exists.
CONSOLE_HOST = "conhost.exe"


class _BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t), ("active_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
                ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", _BasicLimits), ("io", _IoCounters),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]


class _Accounting(ctypes.Structure):
    _fields_ = [("user_time", ctypes.c_int64), ("kernel_time", ctypes.c_int64),
                ("period_user_time", ctypes.c_int64), ("period_kernel_time", ctypes.c_int64),
                ("page_faults", wintypes.DWORD), ("total_processes", wintypes.DWORD),
                ("active_processes", wintypes.DWORD), ("terminated_processes", wintypes.DWORD)]


class _ProcessEntry(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("pid", wintypes.DWORD),
                ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                ("ppid", wintypes.DWORD), ("priority", wintypes.LONG), ("flags", wintypes.DWORD),
                ("exe", wintypes.WCHAR * 260)]


class _WindowsJob:
    def __init__(self) -> None:
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.nt = ctypes.WinDLL("ntdll")
        file_time = ctypes.POINTER(wintypes.FILETIME)
        declarations = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            "QueryInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                           ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "IsProcessInJob": ([wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "TerminateProcess": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            "GetProcessTimes": ([wintypes.HANDLE, file_time, file_time, file_time, file_time], wintypes.BOOL),
            "CreateToolhelp32Snapshot": ([wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
            "Process32FirstW": ([wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)], wintypes.BOOL),
            "Process32NextW": ([wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)], wintypes.BOOL),
        }
        for name, (arguments, result) in declarations.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result
        # NtResumeProcess resumes every thread of a suspended process (psutil's resume() uses it); Popen does not
        # keep the primary thread handle that ResumeThread would need.
        self.nt.NtResumeProcess.argtypes, self.nt.NtResumeProcess.restype = [wintypes.HANDLE], ctypes.c_long
        self.handle = self.api.CreateJobObjectW(None, None)  # Unnamed, non-inheritable handle.
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway allowed.
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def _open(self, pid: int, access: int):
        """A process handle, or None when the PID no longer exists."""
        process = self.api.OpenProcess(access, False, pid)
        if not process:
            if ctypes.get_last_error() == ERROR_INVALID_PARAMETER:
                return None
            raise ctypes.WinError(ctypes.get_last_error())
        return process

    def _close_handle(self, process) -> None:
        if not self.api.CloseHandle(process):
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, pid: int) -> None:
        process = self.api.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.api.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self._close_handle(process)

    def resume(self, pid: int) -> None:
        process = self.api.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            status = self.nt.NtResumeProcess(process)
            if status < 0:
                raise OSError(f"NtResumeProcess failed with NTSTATUS 0x{status & 0xFFFFFFFF:08X}")
        finally:
            self._close_handle(process)

    def count(self) -> int:
        accounting = _Accounting()
        if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(accounting),
                                                  ctypes.sizeof(accounting), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(accounting.active_processes)

    def contains(self, pid: int) -> bool:
        process = self._open(pid, PROCESS_QUERY_LIMITED_INFORMATION)
        if process is None:
            return False
        try:
            member = wintypes.BOOL()
            if not self.api.IsProcessInJob(process, self.handle, ctypes.byref(member)):
                raise ctypes.WinError(ctypes.get_last_error())
            return bool(member.value)
        finally:
            self._close_handle(process)

    def created(self, pid: int) -> int | None:
        """The process's creation time (100 ns ticks), or None when it no longer exists or has exited."""
        process = self._open(pid, PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE)
        if process is None:
            return None
        try:
            if self.api.WaitForSingleObject(process, 0) == 0:  # Exited; only a handle keeps the PID.
                return None
            times = [wintypes.FILETIME() for _ in range(4)]
            if not self.api.GetProcessTimes(process, *(ctypes.byref(t) for t in times)):
                raise ctypes.WinError(ctypes.get_last_error())
            return times[0].dwHighDateTime << 32 | times[0].dwLowDateTime
        finally:
            self._close_handle(process)

    def parents(self) -> dict[int, list[tuple[int, str]]]:
        """Every live process's children (PID, program name), from one system snapshot. Console hosts are left out:
        Windows starts one beside each console program, outside any Job, and ends it with its last client."""
        snapshot = self.api.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS.
        if snapshot in (None, wintypes.HANDLE(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        children: dict[int, list[tuple[int, str]]] = {}
        try:
            entry = _ProcessEntry()
            entry.size = ctypes.sizeof(entry)
            more = self.api.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                if entry.exe.lower() != CONSOLE_HOST:
                    children.setdefault(int(entry.ppid), []).append((int(entry.pid), entry.exe))
                more = self.api.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            self._close_handle(snapshot)
        return children

    def kill(self, pid: int, created: int, wait_ms: int = 5000) -> None:
        """Stop ``pid`` only while it is still the process created at ``created`` (never a reused PID), and wait for
        it to be gone."""
        self._stop(pid, created, wait_ms, terminate=True)

    def wait(self, pid: int, created: int, wait_ms: int = 5000) -> None:
        """Wait for a Job member that is already exiting."""
        self._stop(pid, created, wait_ms, terminate=False)

    def _stop(self, pid: int, created: int, wait_ms: int, terminate: bool) -> None:
        process = self._open(pid, PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE)
        if process is None:
            return
        try:
            if self.created(pid) != created:
                return
            # TerminateProcess on a process that is already exiting fails with access denied; the wait decides.
            if terminate and not self.api.TerminateProcess(process, 1) and ctypes.get_last_error() != 5:
                raise ctypes.WinError(ctypes.get_last_error())
            if self.api.WaitForSingleObject(process, wait_ms) != 0:
                raise TimeoutError(f"process {pid} did not exit within {wait_ms} ms")
        finally:
            self._close_handle(process)

    def terminate(self) -> None:
        if not self.api.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = None


class OwnedProcesses:
    """Returned Popen handles are the commands themselves; each command and every descendant belongs to one Job.

    close() is idempotent and returns true only after the Job reports zero active processes, no descendant found
    before teardown is still alive, and every command is reaped. errors, active_processes, escaped_descendants and
    live_descendants are receipt diagnostics. Assignment failure stops the suspended command before it ever runs.
    """

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("OwnedProcesses requires Windows Job Objects; verified POSIX orphan cleanup is unsupported")
        self.errors: list[str] = []
        self.processes: list[subprocess.Popen] = []
        self.active_processes: int | None = 0
        self.escaped_descendants = 0
        self.live_descendants: int | None = 0
        self._created: dict[int, int] = {}
        self._closed = False
        self._verified = False
        self._job = _WindowsJob()

    def spawn(self, args: list[str], cwd: Path, stream, *, stdin=subprocess.DEVNULL,
              stderr=subprocess.STDOUT) -> subprocess.Popen:
        if self._closed:
            raise RuntimeError("OwnedProcesses is closed")
        if not args or not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
            raise ValueError("Command must be a nonempty list of string arguments")
        process = subprocess.Popen(
            args, cwd=Path(cwd).resolve(), stdin=stdin, stdout=stream, stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW | CREATE_SUSPENDED, close_fds=True,
        )
        self.processes.append(process)
        try:
            self._job.assign(process.pid)
            created = self._job.created(process.pid)
            if created is not None:
                self._created[process.pid] = created
            self._job.resume(process.pid)
            self.active_processes = self._job.count()
            return process
        except BaseException as error:
            self.errors.append(f"spawn/assignment: {type(error).__name__}: {error}")
            try:
                if process.poll() is None:
                    process.kill()  # Still suspended unless resume itself failed after assignment.
                process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError) as stop_error:
                self.errors.append(f"command abort: {stop_error}")
            finally:
                self.close()
            raise

    def owns_pid(self, pid: int) -> bool:
        if self._closed:
            return False
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise ValueError("Expected a positive process ID")
        return self._job.contains(pid)

    def owned_pids(self) -> list[int]:
        return [process.pid for process in self.processes]

    def active_process_count(self) -> int:
        if self._closed:
            if self.active_processes is None:
                raise RuntimeError("Final active process count unavailable")
            return self.active_processes
        self.active_processes = self._job.count()
        return self.active_processes

    def _descendants(self) -> dict[int, tuple[int, str]]:
        """Live descendants of every command (PID -> creation time, program): a child is one whose parent PID is a
        known process and who was created after it, so a reused parent PID never adopts a stranger."""
        children = self._job.parents()
        found: dict[int, tuple[int, str]] = {}
        frontier = list(self._created.items())
        while frontier:
            parent, parent_created = frontier.pop()
            for child, name in children.get(parent, ()):
                if child in found or child in self._created:
                    continue
                created = self._job.created(child)
                if created is not None and created >= parent_created:
                    found[child] = (created, name)
                    frontier.append((child, created))
        return found

    def close(self) -> bool:
        if self._closed:
            return self._verified
        self._closed = True
        descendants: dict[int, tuple[int, str]] = {}
        try:
            descendants = self._descendants()
        except OSError as error:
            self.live_descendants = None
            self.errors.append(f"descendant scan: {type(error).__name__}: {error}")
        try:
            self.active_processes = self._job.count()
            if self.active_processes:
                self._job.terminate()
            deadline = time.monotonic() + 10
            while True:
                self.active_processes = self._job.count()
                if self.active_processes == 0:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Job still has {self.active_processes} active processes")
                time.sleep(0.02)
        except (OSError, TimeoutError) as error:
            self.active_processes = None
            self.errors.append(f"job termination/query: {type(error).__name__}: {error}")
        for pid, (created, name) in descendants.items():
            try:
                if self._job.created(pid) != created:
                    continue
                if self._job.contains(pid):  # A Job member still finishing its exit.
                    self._job.wait(pid, created)
                else:  # Alive after the Job ended and never in it: stop it and say so.
                    self.escaped_descendants += 1
                    self._job.kill(pid, created)
            except (OSError, TimeoutError) as error:
                self.errors.append(f"descendant {name} {pid}: {type(error).__name__}: {error}")
        if self.live_descendants is not None:
            try:
                self.live_descendants = sum(self._job.created(pid) == created
                                            for pid, (created, _) in descendants.items())
            except OSError as error:
                self.live_descendants = None
                self.errors.append(f"descendant recount: {type(error).__name__}: {error}")
        for process in self.processes:
            try:
                process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError) as error:
                self.errors.append(f"command {process.pid}: {type(error).__name__}: {error}")
        try:
            self._job.close()  # KILL_ON_JOB_CLOSE also protects abrupt owner process exit.
        except OSError as error:
            self.errors.append(f"job handle close: {type(error).__name__}: {error}")
        self._verified = (not self.errors and self.active_processes == 0 and self.live_descendants == 0
                          and all(process.poll() is not None for process in self.processes))
        return self._verified
