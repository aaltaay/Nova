"""Actual generated Windows orphan/sibling tests; no services, broker or market inputs."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from nova_chart_processes import OwnedProcesses


@unittest.skipUnless(os.name == "nt", "Windows Job Object integration tests")
class OwnedJobTests(unittest.TestCase):
    def marker_pid(self, marker: Path) -> int:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if marker.exists() and marker.read_text():
                return int(marker.read_text())
            time.sleep(0.02)
        self.fail("Generated child did not write its PID")

    def process_handle(self, pid: int):
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        handle = api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE; identity held through cleanup.
        self.assertTrue(handle)
        return api, handle

    def test_exited_parent_orphan_killed_and_unowned_sibling_preserved(self):
        with tempfile.TemporaryDirectory() as folder, open(os.devnull, "wb") as log:
            marker = Path(folder) / "child.pid"
            owner = OwnedProcesses()
            sibling = subprocess.Popen([sys.executable, "-I", "-S", "-c", "import time;time.sleep(60)"],
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            api = handle = None
            try:
                code = ("import subprocess,sys;from pathlib import Path;"
                        "p=subprocess.Popen([sys.executable,'-I','-S','-c','import time;time.sleep(60)'],"
                        "creationflags=subprocess.CREATE_NO_WINDOW);"
                        "Path(sys.argv[1]).write_text(str(p.pid))")
                parent = owner.spawn([sys.executable, "-I", "-S", "-c", code, str(marker)], Path(folder), log)
                pid = self.marker_pid(marker)
                self.assertEqual(parent.wait(timeout=10), 0)
                self.assertTrue(owner.owns_pid(pid))
                self.assertFalse(owner.owns_pid(sibling.pid))
                self.assertGreater(owner.active_process_count(), 0)
                api, handle = self.process_handle(pid)
                self.assertTrue(owner.close(), owner.errors)
                self.assertEqual(owner.active_processes, 0)
                self.assertEqual(api.WaitForSingleObject(handle, 5000), 0)
                self.assertIsNone(sibling.poll(), "An outside sibling must stay alive")
                self.assertTrue(owner.close(), "Repeated close returns verified result")
            finally:
                owner.close()
                if handle:
                    api.CloseHandle(handle)
                if sibling.poll() is None:
                    sibling.terminate()
                sibling.wait(timeout=5)

    def test_live_parent_and_descendant_are_both_stopped(self):
        with tempfile.TemporaryDirectory() as folder, open(os.devnull, "wb") as log:
            marker = Path(folder) / "child.pid"
            owner = OwnedProcesses()
            try:
                code = ("import subprocess,sys,time;from pathlib import Path;"
                        "p=subprocess.Popen([sys.executable,'-I','-S','-c','import time;time.sleep(60)'],"
                        "creationflags=subprocess.CREATE_NO_WINDOW);"
                        "Path(sys.argv[1]).write_text(str(p.pid));time.sleep(60)")
                parent = owner.spawn([sys.executable, "-I", "-S", "-c", code, str(marker)], Path(folder), log)
                pid = self.marker_pid(marker)
                self.assertIsNone(parent.poll())
                self.assertTrue(owner.owns_pid(pid))
                api, handle = self.process_handle(pid)
                try:
                    self.assertTrue(owner.close(), owner.errors)
                    self.assertIsNotNone(parent.poll())
                    self.assertEqual(api.WaitForSingleObject(handle, 5000), 0)
                finally:
                    api.CloseHandle(handle)
            finally:
                owner.close()

    def test_assignment_failure_never_releases_real_command(self):
        with tempfile.TemporaryDirectory() as folder, open(os.devnull, "wb") as log:
            marker = Path(folder) / "must_not_exist"
            owner = OwnedProcesses()
            command = [sys.executable, "-I", "-S", "-c",
                       "import sys;from pathlib import Path;Path(sys.argv[1]).write_text('launched')", str(marker)]
            try:
                with patch.object(owner._job, "assign", side_effect=OSError("synthetic assignment refusal")):
                    with self.assertRaisesRegex(OSError, "assignment refusal"):
                        owner.spawn(command, Path(folder), log)
                self.assertFalse(marker.exists())
                self.assertTrue(all(p.poll() is not None for p in owner.processes))
                self.assertEqual(owner.active_processes, 0)
                self.assertTrue(owner.errors)
            finally:
                owner.close()

    def test_abrupt_owner_exit_closes_job_and_kills_descendants(self):
        with tempfile.TemporaryDirectory() as folder:
            marker, release = Path(folder) / "child.pid", Path(folder) / "release"
            code = (
                "import os,sys,time;from pathlib import Path;"
                "sys.path.insert(0,sys.argv[1]);from nova_chart_processes import OwnedProcesses;"
                "owner=OwnedProcesses();marker=Path(sys.argv[2]);release=Path(sys.argv[3]);"
                "log=open(os.devnull,'wb');"
                "owner.spawn([sys.executable,'-I','-S','-c',"
                "\"import os,sys,time;from pathlib import Path;Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(60)\","
                "str(marker)],marker.parent,log);"
                "deadline=time.monotonic()+10;"
                "exec('while not release.exists() and time.monotonic()<deadline: time.sleep(.02)');"
                "os._exit(0)"
            )
            parent = subprocess.Popen([sys.executable, "-I", "-S", "-c", code,
                                       str(Path(__file__).resolve().parent), str(marker), str(release)],
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            api = handle = None
            try:
                pid = self.marker_pid(marker)
                api, handle = self.process_handle(pid)
                release.write_text("exit without close()")
                self.assertEqual(parent.wait(timeout=10), 0)
                self.assertEqual(api.WaitForSingleObject(handle, 5000), 0,
                                 "KILL_ON_JOB_CLOSE must survive abrupt owner exit")
            finally:
                if parent.poll() is None:
                    parent.terminate()
                parent.wait(timeout=5)
                if handle:
                    api.CloseHandle(handle)

    def test_invalid_arguments_spawn_nothing(self):
        owner = OwnedProcesses()
        try:
            with patch("nova_chart_processes.subprocess.Popen") as spawn:
                for args in ([], "not argv", [1]):
                    with self.assertRaises(ValueError):
                        owner.spawn(args, Path.cwd(), subprocess.DEVNULL)
                spawn.assert_not_called()
            self.assertTrue(owner.close(), owner.errors)
        finally:
            owner.close()

    def test_closed_owner_refuses_spawn(self):
        owner = OwnedProcesses()
        self.assertTrue(owner.close(), owner.errors)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            owner.spawn([sys.executable], Path.cwd(), subprocess.DEVNULL)

    def test_query_failure_is_explicit_not_verified_cleanup(self):
        owner = OwnedProcesses()
        with patch.object(owner._job, "count", side_effect=OSError("synthetic query refusal")):
            self.assertFalse(owner.close())
        self.assertIsNone(owner.active_processes)
        self.assertTrue(any("query refusal" in error for error in owner.errors))


class UnsupportedPlatformTest(unittest.TestCase):
    def test_posix_does_not_claim_verified_orphan_support(self):
        with patch("nova_chart_processes.os.name", "posix"):
            with self.assertRaisesRegex(RuntimeError, "POSIX orphan cleanup is unsupported"):
                OwnedProcesses()


if __name__ == "__main__":
    unittest.main(verbosity=2)
