"""Own only the isolated processes needed for one frozen-data native Nova export."""
from __future__ import annotations

import hashlib
import json
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
    data_port, renderer_port = _free_ports()
    instance = secrets.token_hex(16)
    data_base, renderer_base = f"http://127.0.0.1:{data_port}", f"http://127.0.0.1:{renderer_port}"
    page = renderer_base + "/chart-gateway.html?" + urllib.parse.urlencode({"api": data_base})
    output.mkdir()
    logs = output / "phase_logs"
    logs.mkdir()
    owned: list[subprocess.Popen] = []
    receipt = dict(schema_version=1, selection_sha256=expected_sha256, ok=False,
                   data_base=data_base, renderer_base=renderer_base, instance=instance,
                   selected_count=len(gallery["entries"]),
                   data_timings=gallery["timings"], source_sha256={
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
                ("renderer", [node, str(vite), "--config", "vite.chart-gateway.config.ts", "--configLoader", "runner",
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
                       cleanup_errors=cleanup_errors, total_command_ms=(time.perf_counter() - began) * 1000)
        if cleanup_errors or not receipt["owned_children_stopped"] or not trees_stopped:
            receipt["ok"] = False
        (output / "EXPORT_RECEIPT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    if not receipt["ok"]:
        raise RuntimeError("Export cleanup incomplete; inspect EXPORT_RECEIPT.json")
    return receipt
