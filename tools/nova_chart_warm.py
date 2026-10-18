"""Warm chart renderer: one long-lived ``vite preview`` and Chromium driver per gateway checkout (#1062).

Usage: py -3 tools/nova_chart_warm.py start [--idle-seconds 600] | status | stop

Owner: the ``serve`` process (started by ``start`` or a ``--warm`` export) owns, in one Job (``OwnedProcesses``), the
renderer and the driver (``nova_chart_export.mjs --serve``); it ends on ``stop``, after ``idle_seconds`` without a
job, or when either child exits, and closes the Job with a verified count. Its rendezvous file
``frontend/.chart-gateway-build/.warm-service.json`` (schema_version 1) is written once ready and removed on shutdown;
a file whose pipe does not answer is a stopped service. Jobs arrive one at a time over an authenticated named pipe as
JSON bytes. Each is checked and verified exactly as the one-shot export; reads of market data never happen here
(#983). Contract: "Warm renderer" in architecture/schema/agent-desk.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from multiprocessing.connection import Client, Listener
from pathlib import Path

import nova_chart_runner as runner
from nova_chart_processes import OwnedProcesses

ROOT = runner.ROOT
BUILDS = ROOT / "frontend" / runner.BUILD_DIR
STATE = BUILDS / ".warm-service.json"
LOG = BUILDS / ".warm-service.log"
SCHEMA_VERSION = 1
DEFAULT_IDLE_SECONDS, MAX_IDLE_SECONDS = 600, 3600
START_TIMEOUT_SECONDS = 90
JOB_TIMEOUT_SECONDS = 120
DRIVER_EXIT_SECONDS = 10
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
SOURCES = ("tools/nova_chart_warm.py", "tools/nova_chart_runner.py", "tools/nova_chart_export.mjs",
           "tools/nova_chart_processes.py", "frontend/vite.chart-gateway.config.ts")


class WarmUnavailable(RuntimeError):
    """No warm renderer could be reached or started; the message says why."""


def _log(line: str) -> None:
    BUILDS.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(f"{datetime.now(timezone.utc).isoformat()} pid={os.getpid()} {line}\n")


def _source_hashes() -> dict[str, str]:
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def _idle(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_IDLE_SECONDS:
        raise ValueError(f"idle_seconds is a whole number from 1 through {MAX_IDLE_SECONDS}")
    return value


class _Service:
    def __init__(self, idle_seconds: int) -> None:
        self.idle_seconds = _idle(idle_seconds)
        self.owner = OwnedProcesses()
        self.stopping = threading.Event()
        self.jobs = 0
        self.last = time.monotonic()
        self.busy = threading.Lock()
        self.replies: queue.Queue = queue.Queue()
        self.key = secrets.token_bytes(32)
        self.pipe = r"\\.\pipe\nova-chart-warm-" + secrets.token_hex(8)
        self.sources = _source_hashes()

    def start(self) -> None:
        node, vite = shutil.which("node"), ROOT / "frontend/node_modules/vite/bin/vite.js"
        if not node or not vite.is_file():
            raise RuntimeError("Use the project's installed Node/Vite dependencies; no packages are installed here")
        self.bundle = runner._gateway_bundle(node, vite)
        port = runner._free_ports()[1]
        self.instance = secrets.token_hex(16)
        self.base = f"http://127.0.0.1:{port}"
        self.page = self.base + "/chart-gateway.html?" + urllib.parse.urlencode({"api": self.base})
        renderer_log = (BUILDS / ".warm-renderer.log").open("wb")
        driver_log = (BUILDS / ".warm-driver.log").open("wb")
        self.renderer = self.owner.spawn(
            [node, str(vite), "preview", "--config", "vite.chart-gateway.config.ts", "--configLoader", "runner",
             "--outDir", str(self.bundle), "--strictPort", "--port", str(port), "--host", "127.0.0.1",
             "--mode", self.instance], ROOT / "frontend", renderer_log)
        runner._ready(self.page, self.renderer, self.instance)
        self.driver = self.owner.spawn([node, str(ROOT / "tools/nova_chart_export.mjs"), "--serve", "--url", self.page],
                                       ROOT, subprocess.PIPE, stdin=subprocess.PIPE, stderr=driver_log)
        threading.Thread(target=self._read_driver, daemon=True).start()
        self.listener = Listener(self.pipe, family="AF_PIPE", authkey=self.key)
        state = dict(schema_version=SCHEMA_VERSION, pid=os.getpid(), pipe=self.pipe, authkey=self.key.hex(),
                     bundle=self.bundle.name, renderer_base=self.base, instance=self.instance,
                     idle_seconds=self.idle_seconds, started_utc=datetime.now(timezone.utc).isoformat())
        staging = STATE.with_name(f".warm-service.{secrets.token_hex(4)}.tmp")
        staging.write_text(json.dumps(state), encoding="utf-8")
        os.replace(staging, STATE)
        _log(f"ready renderer={self.base} bundle={self.bundle.name} owned={self.owner.owned_pids()}")

    def _read_driver(self) -> None:
        for line in self.driver.stdout:
            self.replies.put(line)
        self.replies.put(None)

    def status(self) -> dict:
        return dict(ok=True, running=True, pid=os.getpid(), owned_pids=self.owner.owned_pids(),
                    live_owned_processes=self.owner.active_process_count(), jobs_served=self.jobs,
                    idle_seconds=self.idle_seconds, idle_left_s=round(self.idle_seconds - (time.monotonic() - self.last)),
                    renderer_base=self.base, renderer_bundle=self.bundle.name)

    def serve(self) -> None:
        threading.Thread(target=self._accept, daemon=True).start()
        while not self.stopping.wait(0.5):
            if self.renderer.poll() is not None or self.driver.poll() is not None:
                _log(f"a child exited (renderer {self.renderer.poll()}, driver {self.driver.poll()}); stopping")
                break
            if time.monotonic() - self.last > self.idle_seconds and self.busy.acquire(blocking=False):
                self.busy.release()
                _log(f"idle {self.idle_seconds} s; stopping")
                break

    def _accept(self) -> None:
        while not self.stopping.is_set():
            try:
                connection = self.listener.accept()
            except Exception as error:  # A refused handshake or the listener closing on shutdown.
                if not self.stopping.is_set():
                    _log(f"connection refused: {type(error).__name__}")
                continue
            with connection, self.busy:
                self._handle(connection)
                self.last = time.monotonic()

    def _handle(self, connection) -> None:
        try:
            request = json.loads(connection.recv_bytes(MAX_MESSAGE_BYTES))
            op = request.get("op") if isinstance(request, dict) else None
            if op == "status":
                reply = self.status()
            elif op == "stop":
                reply = dict(ok=True, stopping=True)
            elif op == "export":
                reply = self._export(request)
            else:
                reply = dict(ok=False, error="unknown op")
            connection.send_bytes(json.dumps(reply, allow_nan=False).encode())
            if op == "stop":  # Only after the caller has its answer.
                self.stopping.set()
        except (OSError, EOFError, ValueError) as error:
            _log(f"job channel error: {type(error).__name__}: {error}")

    def _export(self, request: dict) -> dict:
        began = time.perf_counter()
        selection, output = Path(request["selection"]).resolve(), Path(request["output"]).resolve()
        sha, samples = request["sha256"], request["samples"]
        if isinstance(samples, bool) or not isinstance(samples, int) or not 0 <= samples <= 50:
            return dict(ok=False, error="samples must be0..50")
        if output.exists():
            return dict(ok=False, error="Existing output preserved; choose a new directory")
        sys.path.insert(0, str(ROOT / "backend"))
        from agent_desk.chart_gallery import load_gallery
        try:
            gallery = load_gallery(selection, sha)
        except (OSError, ValueError) as error:
            return dict(ok=False, error=f"selection refused: {error}")
        current = {}
        hashing = threading.Thread(target=lambda: current.update(key=runner._bundle_key(ROOT / "frontend"),
                                                                 sources=_source_hashes()))
        hashing.start()
        output.mkdir()
        self.jobs += 1
        receipt = dict(schema_version=1, selection_sha256=sha, ok=False, renderer="warm", renderer_base=self.base,
                       instance=self.instance, selected_count=len(gallery["entries"]),
                       renderer_bundle=self.bundle.name, renderer_bundle_ms=0.0, data_timings=gallery["timings"],
                       source_sha256=self.sources)
        try:
            job = dict(id=self.jobs, url=self.page, output=str(output / "images"), samples=samples,
                       gallery=json.dumps(gallery, allow_nan=False, separators=(",", ":")))
            self.driver.stdin.write((json.dumps(job) + "\n").encode())
            self.driver.stdin.flush()
            try:
                line = self.replies.get(timeout=JOB_TIMEOUT_SECONDS)
            except queue.Empty as error:
                self.stopping.set()
                raise RuntimeError(f"The warm driver did not answer within {JOB_TIMEOUT_SECONDS} s; stopping") from error
            answer = json.loads(line) if line else None
            if not answer or answer.get("id") != self.jobs:
                self.stopping.set()
                raise RuntimeError("The warm driver exited or answered out of turn; stopping")
            if not answer["ok"]:
                raise RuntimeError(f"Native export failed: {answer.get('error')}")
            verify = output / "images/CAPTURE_VERIFICATION.json"
            report = json.loads(verify.read_text(encoding="utf-8"))
            if report["errors"] or report["blocked_requests"]:
                raise RuntimeError("Browser verification did not pass")
            images = sorted((output / "images").glob("*.png"))
            if len(images) != len(gallery["entries"]) + 2:
                raise RuntimeError("Expected overview, paired examples and view-verification image")
            load_gallery(selection, sha)  # Verify all frozen bytes again after capture.
            hashing.join()
            if (current.get("key") != self.bundle.name or current.get("sources") != self.sources
                    or not (self.bundle / "chart-gateway.html").is_file()):
                self.stopping.set()
                raise RuntimeError("stale: the renderer or its tools changed since this warm renderer started")
            receipt.update(ok=True, images=[str(p) for p in images],
                           image_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in images},
                           capture_verification=str(verify), source_data_mutated=False, broker_or_desk_calls=False)
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            receipt.update(error_type=type(error).__name__, error=str(error))
        finally:
            hashing.join()
            receipt.update(cleanup_errors=list(self.owner.errors), total_command_ms=(time.perf_counter() - began) * 1000,
                           warm_service=dict(pid=os.getpid(), owned_pids=self.owner.owned_pids(),
                                             live_owned_processes=self.owner.active_process_count(),
                                             jobs_served=self.jobs, idle_seconds=self.idle_seconds))
            (output / "EXPORT_RECEIPT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return dict(ok=receipt["ok"], receipt=receipt, error=receipt.get("error"))

    def shutdown(self) -> bool:
        # The accept thread is a daemon: it ends with this process, and so does the pipe. Removing the rendezvous
        # file first means no new caller finds it; one already connecting gets a broken pipe and starts afresh.
        self.stopping.set()
        try:
            if json.loads(STATE.read_text(encoding="utf-8")).get("pid") == os.getpid():
                STATE.unlink()
        except (OSError, ValueError):
            pass  # maintainer: allow-swallow another service owns or removed the rendezvous file
        if self.driver.poll() is None:
            self.driver.stdin.close()  # The driver closes Chromium and exits on end of input.
            try:
                self.driver.wait(timeout=DRIVER_EXIT_SECONDS)
            except subprocess.TimeoutExpired:
                _log(f"driver did not exit within {DRIVER_EXIT_SECONDS} s; the Job ends it")
        verified = self.owner.close()
        _log(f"stopped verified={verified} active={self.owner.active_processes} live_descendants="
             f"{self.owner.live_descendants} escaped={self.owner.escaped_descendants} errors={self.owner.errors}")
        return verified


def _call_raw(pipe: str, key: bytes, request: dict, timeout: float) -> dict:
    connection = Client(pipe, family="AF_PIPE", authkey=key)
    with connection:
        connection.send_bytes(json.dumps(request).encode())
        if not connection.poll(timeout):
            raise WarmUnavailable(f"The warm renderer did not answer within {timeout:.0f} s")
        return json.loads(connection.recv_bytes(MAX_MESSAGE_BYTES))


def _state() -> dict | None:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        raise WarmUnavailable(f"{STATE} has an unknown schema_version; stop that renderer or remove the file")
    return state


def _call(request: dict, timeout: float) -> dict | None:
    """The running service's answer, or None when there is none (a stale rendezvous file is removed)."""
    state = _state()
    if state is None:
        return None
    try:
        return _call_raw(state["pipe"], bytes.fromhex(state["authkey"]), request, timeout)
    except (FileNotFoundError, ConnectionRefusedError, EOFError):
        STATE.unlink(missing_ok=True)
        return None


def status() -> dict:
    return _call({"op": "status"}, 10) or dict(ok=True, running=False)


def start(idle_seconds: int = DEFAULT_IDLE_SECONDS) -> dict:
    """The running service's status, starting one (detached, owner of its own Job) when none answers."""
    _idle(idle_seconds)
    current = _call({"op": "status"}, 10)
    if current:
        return current
    BUILDS.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "serve",
                                    "--idle-seconds", str(idle_seconds)], cwd=ROOT, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, close_fds=True,
                                   creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        current = _call({"op": "status"}, 10)
        if current:
            return current
        if process.poll() is not None and _state() is None:
            raise WarmUnavailable(f"The warm renderer exited {process.returncode} while starting; see {LOG}")
        time.sleep(0.1)
    raise WarmUnavailable(f"The warm renderer was not ready within {START_TIMEOUT_SECONDS} s; see {LOG}")


def stop() -> dict:
    answer = _call({"op": "stop"}, 10)
    if not answer:
        return dict(ok=True, running=False)
    deadline = time.monotonic() + 30
    while STATE.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    return dict(ok=not STATE.exists(), stopped=True)


def export(selection: Path, sha256: str, output: Path, samples: int = 0,
           idle_seconds: int = DEFAULT_IDLE_SECONDS) -> dict:
    """The one-shot export's inputs and receipt, drawn by the warm renderer (started when none is running)."""
    for attempt in (1, 2):
        start(idle_seconds)
        answer = _call({"op": "export", "selection": str(selection), "sha256": sha256, "output": str(output),
                        "samples": samples}, JOB_TIMEOUT_SECONDS + 30)
        if answer is None:
            raise WarmUnavailable("The warm renderer stopped before answering")
        stale = str(answer.get("error") or "").startswith("stale")
        if answer["ok"] or not stale or attempt == 2:
            if not answer["ok"]:
                raise RuntimeError(f"Warm export failed: {answer.get('error')}")
            return answer["receipt"]
        shutil.rmtree(output, ignore_errors=True)  # Only this call's refused output; the next renderer redraws it.
        stop()
    raise AssertionError("unreachable")


def _serve(idle_seconds: int) -> int:
    if _call({"op": "status"}, 10):
        _log("another warm renderer answers for this checkout; not starting a second")
        return 3
    service = _Service(idle_seconds)
    try:
        service.start()
        service.serve()
    except Exception as error:
        _log(f"failed: {type(error).__name__}: {error}")
        raise
    finally:
        verified = service.shutdown() if hasattr(service, "listener") else service.owner.close()
    return 0 if verified else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["start", "status", "stop", "serve"])
    parser.add_argument("--idle-seconds", type=int, default=DEFAULT_IDLE_SECONDS)
    args = parser.parse_args(argv)
    if args.command == "serve":
        return _serve(args.idle_seconds)
    try:
        result = {"start": lambda: start(args.idle_seconds), "status": status, "stop": stop}[args.command]()
    except (WarmUnavailable, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
