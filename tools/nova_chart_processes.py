"""Own a Windows Job tree from before real commands start until verified teardown.

Only standard-library code runs in the bootstrap, with site initialization off.
Unsupported platforms fail clearly rather than promise orphan cleanup they cannot verify.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time


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


class _WindowsJob:
    def __init__(self) -> None:
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
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
        }
        for name, (arguments, result) in declarations.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.api.CreateJobObjectW(None, None)  # Unnamed, non-inheritable handle.
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway allowed.
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, pid: int) -> None:
        process = self.api.OpenProcess(0x0101, False, pid)  # PROCESS_SET_QUOTA | PROCESS_TERMINATE.
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.api.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if not self.api.CloseHandle(process):
                raise ctypes.WinError(ctypes.get_last_error())

    def count(self) -> int:
        accounting = _Accounting()
        if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(accounting),
                                                  ctypes.sizeof(accounting), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(accounting.active_processes)

    def contains(self, pid: int) -> bool:
        process = self.api.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION.
        if not process:
            if ctypes.get_last_error() == 87:  # PID no longer exists.
                return False
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            member = wintypes.BOOL()
            if not self.api.IsProcessInJob(process, self.handle, ctypes.byref(member)):
                raise ctypes.WinError(ctypes.get_last_error())
            return bool(member.value)
        finally:
            if not self.api.CloseHandle(process):
                raise ctypes.WinError(ctypes.get_last_error())

    def terminate(self) -> None:
        if not self.api.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = None


class OwnedProcesses:
    """Returned Popen handles supervise commands; every command descendant belongs to one Job.

    close() is idempotent, returns true only after querying zero active Job processes
    and reaping direct supervisors. errors and active_processes are receipt diagnostics.
    Assignment failure never releases the stdin gate or starts the real command.
    """

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("OwnedProcesses requires Windows Job Objects; verified POSIX orphan cleanup is unsupported")
        self.errors: list[str] = []
        self.processes: list[subprocess.Popen] = []
        self.active_processes: int | None = 0
        self._closed = False
        self._verified = False
        self._job = _WindowsJob()

    def spawn(self, args: list[str], cwd: Path, stream) -> subprocess.Popen:
        if self._closed:
            raise RuntimeError("OwnedProcesses is closed")
        if not args or not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
            raise ValueError("Command must be a nonempty list of string arguments")
        payload = json.dumps({"protocol": 1, "args": args, "cwd": str(Path(cwd).resolve())}).encode() + b"\n"
        process = subprocess.Popen(
            [sys.executable, "-I", "-S", "-B", "-u", str(Path(__file__).resolve()), "--owned-bootstrap"],
            cwd=cwd, stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True,
        )
        self.processes.append(process)
        try:
            self._job.assign(process.pid)
            assert process.stdin is not None
            process.stdin.write(payload)
            process.stdin.flush()
            process.stdin.close()
            self.active_processes = self._job.count()
            return process
        except BaseException as error:
            self.errors.append(f"spawn/assignment: {type(error).__name__}: {error}")
            # Before assignment succeeds this bootstrap owns no command descendants.
            try:
                if process.stdin is not None and not process.stdin.closed:
                    try:
                        process.stdin.close()
                    except OSError as close_error:
                        self.errors.append(f"bootstrap stdin close: {close_error}")
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError) as stop_error:
                self.errors.append(f"bootstrap abort: {stop_error}")
            finally:
                self.close()
            raise

    def owns_pid(self, pid: int) -> bool:
        if self._closed:
            return False
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise ValueError("Expected a positive process ID")
        return self._job.contains(pid)

    def active_process_count(self) -> int:
        if self._closed:
            if self.active_processes is None:
                raise RuntimeError("Final active process count unavailable")
            return self.active_processes
        self.active_processes = self._job.count()
        return self.active_processes

    def close(self) -> bool:
        if self._closed:
            return self._verified
        self._closed = True
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
        for process in self.processes:
            try:
                process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError) as error:
                self.errors.append(f"supervisor {process.pid}: {type(error).__name__}: {error}")
        try:
            self._job.close()  # KILL_ON_JOB_CLOSE also protects abrupt owner process exit.
        except OSError as error:
            self.errors.append(f"job handle close: {type(error).__name__}: {error}")
        self._verified = (not self.errors and self.active_processes == 0
                          and all(process.poll() is not None for process in self.processes))
        return self._verified


def _bootstrap() -> int:
    line = sys.stdin.buffer.readline()
    if not line:  # Assignment failed: stdin closes without releasing a command.
        return 125
    request = json.loads(line)
    if request.get("protocol") != 1:
        raise ValueError("Unknown owned bootstrap protocol")
    child = subprocess.Popen(request["args"], cwd=request["cwd"], stdin=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
    return child.wait()


if __name__ == "__main__":
    if sys.argv[1:] != ["--owned-bootstrap"] or os.name != "nt":
        raise SystemExit("Internal Windows owned-process bootstrap only")
    raise SystemExit(_bootstrap())
