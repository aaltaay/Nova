"""Own only the isolated processes needed for one frozen-data native Nova export.

The chart-only renderer is a production Vite build, served by ``vite preview``: a dev server spent ~9 s of every
export compiling modules on the first page load. Owner of ``frontend/.chart-gateway-build/<key>/`` (no schema: a
build artifact); invalidated when any frontend source, the gateway page or config, or the lockfile changes (``key``).
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import ExitStack
from pathlib import Path

from nova_chart_processes import OwnedProcesses

ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ".chart-gateway-build"
BUILD_TIMEOUT_SECONDS = 300
BUILD_INPUTS = ("chart-gateway.html", "vite.chart-gateway.config.ts", "package-lock.json")
# Waits before each further try to move a new build into place: Windows can refuse the rename while something holds
# a file in the new folder for a moment (#1084). Bounded: about 4 s in all.
RENAME_RETRY_PAUSES = (0.1, 0.25, 0.5, 1.0, 2.0)


def _bundle_key(frontend: Path) -> str:
    """Every renderer input's path, size and modification time: an edit anywhere rebuilds."""
    digest = hashlib.sha256()
    files = [frontend / name for name in BUILD_INPUTS]
    for folder, _, names in os.walk(frontend / "src"):
        files += [Path(folder) / name for name in names]
    for path in sorted(files):
        info = path.stat()
        digest.update(f"{path.relative_to(frontend).as_posix()}|{info.st_size}|{info.st_mtime_ns}\n".encode())
    return digest.hexdigest()[:20]


def _move_into_place(staging: Path, bundle: Path) -> None:
    """Rename the new build to its key. A concurrent export that built the same key first wins: its bundle is used
    once its page is there, and this build is dropped. A refusal with no complete bundle in place is tried again
    (``RENAME_RETRY_PAUSES``), then says which folders and why; a folder without its page is never used (#1084)."""
    page = bundle / "chart-gateway.html"
    error: OSError | None = None
    for pause in (0.0, *RENAME_RETRY_PAUSES):
        time.sleep(pause)
        try:
            staging.rename(bundle)
            return
        except OSError as refused:
            error = refused
        if page.is_file():
            shutil.rmtree(staging, ignore_errors=True)
            return
    shutil.rmtree(staging, ignore_errors=True)
    if bundle.exists():
        there = f"{bundle} holds no chart-gateway.html: it is no renderer build; delete it and export again"
    else:
        there = (f"{bundle} does not exist: a process watching or scanning {bundle.parent} holds the new folder "
                 "open; the next export builds again")
    raise RuntimeError(
        f"Chart renderer build could not be moved into place: renaming {staging} to {bundle} was refused "
        f"{1 + len(RENAME_RETRY_PAUSES)} times in {sum(RENAME_RETRY_PAUSES):.1f} s ({error}). {there}"
    ) from error


def _gateway_bundle(node: str, vite: Path) -> Path:
    """The built chart-only renderer for the current sources, building it once (into a temp folder, then moved)."""
    frontend = ROOT / "frontend"
    builds = frontend / BUILD_DIR
    bundle = builds / _bundle_key(frontend)
    if (bundle / "chart-gateway.html").is_file():
        return bundle
    staging = builds / f".tmp-{secrets.token_hex(6)}"
    builds.mkdir(exist_ok=True)
    result = subprocess.run([node, str(vite), "build", "--config", "vite.chart-gateway.config.ts",
                             "--configLoader", "runner", "--outDir", str(staging), "--emptyOutDir",
                             "--logLevel", "warn"], cwd=frontend, capture_output=True, text=True,
                            timeout=BUILD_TIMEOUT_SECONDS, check=False)
    if result.returncode or not (staging / "chart-gateway.html").is_file():
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError(f"Chart renderer build failed: {(result.stderr or result.stdout)[-2000:]}")
    _move_into_place(staging, bundle)
    for old in builds.iterdir():  # Dot names are in-flight builds and the warm renderer's files.
        if old != bundle and not old.name.startswith("."):
            shutil.rmtree(old, ignore_errors=True)
    return bundle


def _free_ports() -> tuple[int, int]:
    with socket.socket() as data, socket.socket() as renderer:
        data.bind(("127.0.0.1", 0))
        renderer.bind(("127.0.0.1", 0))
        return data.getsockname()[1], renderer.getsockname()[1]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def _ready(url: str, process: subprocess.Popen, instance: str,
           expected_sha: str | None = None) -> None:
    target = urllib.parse.urlsplit(url)
    if target.scheme != "http" or target.hostname != "127.0.0.1":
        raise ValueError("Readiness requires explicit IPv4 loopback HTTP")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Isolated child exited {process.returncode}; inspect phase logs")
        try:
            with opener.open(url, timeout=1) as response:
                body = response.read()
                if response.status != 200 or response.headers.get("X-Nova-Chart-Instance") != instance:
                    raise ValueError("Isolated service instance identity mismatch; possible port collision")
                if response.geturl() != url:
                    raise ValueError("Readiness response URL changed")
            if expected_sha is None or json.loads(body).get("selection_sha256") == expected_sha:
                return
            raise ValueError("Isolated service selection identity mismatch")
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Isolated readiness refused HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.05)
    raise TimeoutError("Isolated chart service did not become ready within30seconds")


def export_charts(selection: Path, expected_sha256: str, output: Path, samples: int = 0) -> dict:
    """Validate before starting processes; no .env, trading lifespan or market requests."""
    began = time.perf_counter()
    selection, output = selection.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError("Existing output preserved; choose a new directory")
    if isinstance(samples, bool) or not isinstance(samples, int) or not 0 <= samples <= 50:
        raise ValueError("samples must be0..50")
    sys.path.insert(0, str(ROOT / "backend"))
    from agent_desk.chart_gallery import load_gallery
    gallery = load_gallery(selection, expected_sha256)
    node = shutil.which("node")
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    if not node or not vite.is_file():
        raise RuntimeError("Use the project's installed Node/Vite dependencies; no packages are installed by this command")
    built = time.perf_counter()
    bundle = _gateway_bundle(node, vite)
    bundle_ms = (time.perf_counter() - built) * 1000
    data_port, renderer_port = _free_ports()
    instance = secrets.token_hex(16)
    data_base, renderer_base = f"http://127.0.0.1:{data_port}", f"http://127.0.0.1:{renderer_port}"
    page = renderer_base + "/chart-gateway.html?" + urllib.parse.urlencode({"api": data_base})
    output.mkdir()
    logs = output / "phase_logs"
    logs.mkdir()
    owned: list[subprocess.Popen] = []
    receipt = dict(schema_version=1, selection_sha256=expected_sha256, ok=False, renderer="cold",
                   data_base=data_base, renderer_base=renderer_base, instance=instance,
                   selected_count=len(gallery["entries"]), renderer_bundle=bundle.name,
                   renderer_bundle_ms=bundle_ms, data_timings=gallery["timings"], source_sha256={
                       str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in [ROOT / "tools/nova_charts.py", Path(__file__).resolve(),
                                 ROOT / "tools/nova_chart_export.mjs", ROOT / "tools/nova_chart_processes.py",
                                 ROOT / "frontend/vite.chart-gateway.config.ts"]})
    owner = None
    try:
        owner = OwnedProcesses()
        with ExitStack() as stack:
            for name, args, cwd in [
                ("data", [sys.executable, "-B", str(ROOT / "tools/nova_charts.py"), "serve",
                          "--selection", str(selection), "--sha256", expected_sha256,
                          "--port", str(data_port), "--frontend-origin", renderer_base,
                          "--instance", instance], ROOT),
                ("renderer", [node, str(vite), "preview", "--config", "vite.chart-gateway.config.ts",
                              "--configLoader", "runner", "--outDir", str(bundle), "--strictPort",
                              "--port", str(renderer_port), "--host", "127.0.0.1",
                              "--mode", instance], ROOT / "frontend"),
            ]:
                owned.append(owner.spawn(args, cwd, stack.enter_context((logs / f"{name}.log").open("xb"))))
            receipt["owned_pids"] = [p.pid for p in owned]
            _ready(data_base + "/api/agent/chart-gallery", owned[0], instance, expected_sha256)
            _ready(page, owned[1], instance)
            receipt["services_ready_ms"] = (time.perf_counter() - began) * 1000
            exporter = owner.spawn([node, str(ROOT / "tools/nova_chart_export.mjs"), "--url", page,
                               "--api-url", data_base, "--output", str(output / "images"),
                               "--samples", str(samples)], ROOT,
                              stack.enter_context((logs / "export.log").open("xb")))
            owned.append(exporter)
            receipt["owned_pids"].append(exporter.pid)
            code = exporter.wait(timeout=120)
            if code != 0:
                raise RuntimeError(f"Native export exited {code}; inspect phase_logs/export.log")
            verify = output / "images/CAPTURE_VERIFICATION.json"
            if not verify.is_file():
                raise RuntimeError("Native export omitted verification receipt")
            report = json.loads(verify.read_text(encoding="utf-8"))
            if report["errors"] or report["blocked_requests"]:
                raise RuntimeError("Browser verification did not pass")
            images = sorted((output / "images").glob("*.png"))
            if len(images) != len(gallery["entries"]) + 2:
                raise RuntimeError("Expected overview, paired examples and view-verification image")
            load_gallery(selection, expected_sha256)  # Verify all frozen bytes again after capture.
            receipt.update(ok=True, images=[str(p) for p in images],
                           image_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in images},
                           capture_verification=str(verify), source_data_mutated=False,
                           broker_or_desk_calls=False)
    except Exception as error:
        receipt.update(error_type=type(error).__name__, error=str(error))
        raise
    finally:
        trees_stopped = owner.close() if owner else True
        cleanup_errors = owner.errors if owner else []
        receipt.update(owned_children_stopped=all(p.poll() is not None for p in owned),
                       owned_trees_stopped=trees_stopped, active_owned_processes=owner.active_processes if owner else 0,
                       live_descendants_after_cleanup=owner.live_descendants if owner else 0,
                       escaped_job_descendants=owner.escaped_descendants if owner else 0,
                       cleanup_errors=cleanup_errors, total_command_ms=(time.perf_counter() - began) * 1000)
        if (cleanup_errors or not receipt["owned_children_stopped"] or not trees_stopped
                or receipt["live_descendants_after_cleanup"] != 0):
            receipt["ok"] = False
        (output / "EXPORT_RECEIPT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    if not receipt["ok"]:
        raise RuntimeError("Export cleanup incomplete; inspect EXPORT_RECEIPT.json")
    return receipt
