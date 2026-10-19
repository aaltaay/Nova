"""The chart MCP server's warm renderer: started by the long-lived server, outside every call's Job (#1062).

Owner: the MCP server process, of at most one ``nova_chart_warm.py serve`` from the gateway checkout at a time, each in
a Job of its own (the gateway's ``OwnedProcesses``). A trade-chart call asks ``ensure`` first: the pid of the warm
renderer that answers for the gateway, starting one in this server's Job when none does, so the call's own Job (torn
down and verified after every call) never holds the renderer. The renderer stops itself after ``idle_seconds``
without a job, the same 10 minutes as ``--warm``; the next ``ensure`` closes its Job, verified (``reaped``). ``close``
stops it at server exit and verifies its Job is empty. If the server dies abruptly its Job closes, which ends the
renderer, and the renderer's own Job then ends the browser and ``vite preview``. A renderer someone else started
(``--warm`` from a shell) is used and left alone. Contract: "Warm renderer" in architecture/schema/agent-desk.md.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

IDLE_SECONDS = 600
MAX_IDLE_SECONDS = 3600
START_TIMEOUT_SECONDS = 90
STOP_TIMEOUT_SECONDS = 30


class WarmRendererUnavailable(RuntimeError):
    """No warm renderer answers and none could be started; the message says why."""


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None or not path.is_file():
        raise WarmRendererUnavailable(f"{path} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WarmRenderer:
    def __init__(self, gateway: Path, python: Path, idle_seconds: int = IDLE_SECONDS) -> None:
        if isinstance(idle_seconds, bool) or not isinstance(idle_seconds, int) or not 1 <= idle_seconds <= MAX_IDLE_SECONDS:
            raise ValueError(f"idle_seconds is a whole number from 1 through {MAX_IDLE_SECONDS}")
        self.gateway, self.python, self.idle_seconds = gateway, python, idle_seconds
        self.script = gateway / "tools" / "nova_chart_warm.py"
        self.reaped: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._warm = self._processes = self._owner = self._process = self._log = None

    def _modules(self):
        if self._warm is None:
            tools = str(self.gateway / "tools")
            if tools not in sys.path:
                sys.path.insert(0, tools)  # The warm module's own imports come from the same checkout.
            self._processes = _load(self.gateway / "tools" / "nova_chart_processes.py", "_nova_chart_mcp_warm_owned")
            self._warm = _load(self.script, "_nova_chart_mcp_warm_service")
        return self._warm, self._processes

    def ensure(self) -> int:
        """The answering warm renderer's pid, starting one in this server's Job when none answers."""
        with self._lock:
            warm, processes = self._modules()
            current = warm.status()
            if current.get("running"):
                return int(current["pid"])
            self._reap()
            log = getattr(warm, "LOG", None)
            if log is not None:
                Path(log).parent.mkdir(parents=True, exist_ok=True)
                self._log = open(log, "ab")
            self._owner = processes.OwnedProcesses()
            self._process = self._owner.spawn(
                [str(self.python), "-B", str(self.script), "serve", "--idle-seconds", str(self.idle_seconds)],
                self.gateway, self._log if self._log is not None else subprocess.DEVNULL)
            deadline = time.monotonic() + START_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                current = warm.status()
                if current.get("running"):
                    return int(current["pid"])
                if self._process.poll() is not None:
                    code = self._process.returncode
                    self._reap()
                    raise WarmRendererUnavailable(f"The warm renderer exited {code} while starting")
                time.sleep(0.1)
            self._reap()
            raise WarmRendererUnavailable(f"The warm renderer was not ready within {START_TIMEOUT_SECONDS} s")

    def _reap(self) -> dict[str, Any] | None:
        """Close the Job of a renderer this server started (waiting for one that is already stopping)."""
        if self._process is None:
            return None
        try:
            code = self._process.wait(timeout=STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            code = None  # Still running: closing the Job ends it.
        record = dict(pid=self._process.pid, verified=self._owner.close(), exit_code=code)
        self.reaped.append(record)
        if self._log is not None:
            self._log.close()
        self._owner = self._process = self._log = None
        return record

    def close(self) -> dict[str, Any]:
        """Stop the renderer this server started and verify its Job is empty; one it did not start is left running."""
        with self._lock:
            if self._process is None:
                return dict(stopped=False, verified=True, exit_code=None, live_descendants=0)
            stopped = False
            if self._process.poll() is None:
                current = self._warm.status()
                if current.get("running") and current.get("pid") == self._process.pid:
                    stopped = bool(self._warm.stop().get("stopped"))
            owner = self._owner
            record = self._reap()
            return dict(stopped=stopped, verified=record["verified"], exit_code=record["exit_code"],
                        live_descendants=owner.live_descendants)
