"""Generated orchestration guards; no real services, broker, charts or market inputs."""
import json
import subprocess
import sys
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import nova_chart_runner as runner


def no_children(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("No child may start for invalid input")
    monkeypatch.setattr(runner, "OwnedProcesses", refuse)


def test_missing_data_starts_no_children(tmp_path, monkeypatch):
    no_children(monkeypatch)
    output = tmp_path / "new"
    with pytest.raises(FileNotFoundError):
        runner.export_charts(tmp_path / "missing.json", "0" * 64, output)
    assert not output.exists()


def test_existing_output_is_preserved(tmp_path, monkeypatch):
    no_children(monkeypatch)
    output = tmp_path / "existing"
    output.mkdir()
    original = output / "keep.txt"
    original.write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError):
        runner.export_charts(tmp_path / "missing.json", "0" * 64, output)
    assert original.read_text(encoding="utf-8") == "preserve"


def test_bad_hash_starts_no_children(tmp_path, monkeypatch):
    no_children(monkeypatch)
    selection = tmp_path / "selection.json"
    selection.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Selection SHA256"):
        runner.export_charts(selection, "0" * 64, tmp_path / "new")
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("samples", [-1, 51])
def test_bad_benchmark_budget_starts_no_children(tmp_path, monkeypatch, samples):
    no_children(monkeypatch)
    with pytest.raises(ValueError, match="samples"):
        runner.export_charts(tmp_path / "missing.json", "0" * 64, tmp_path / "new", samples)


class FakeProcess:
    pid = 999999
    stopped = False
    def poll(self):
        return 0 if self.stopped else None
    def wait(self, timeout):
        self.stopped = True
        return 0


@pytest.mark.parametrize("status,instance,error", [
    (200, "another-service", ValueError), (302, "expected", RuntimeError),
])
def test_readiness_refuses_colliding_service_and_redirect(status, instance, error, monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("X-Nova-Chart-Instance", instance)
            self.send_header("Location", "http://127.0.0.1:1/do-not-follow")
            self.end_headers()
            self.wfile.write(b'{}')
        def log_message(self, *args):
            return
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
        monkeypatch.setenv("no_proxy", "")
        collider = FakeProcess()
        try:
            with pytest.raises(error):
                runner._ready(f"http://127.0.0.1:{server.server_port}/", collider, "expected")
            assert not collider.stopped
        finally:
            server.shutdown()
            thread.join()


def test_readiness_rejects_nonlocal_before_network():
    with pytest.raises(ValueError, match="loopback"):
        runner._ready("http://example.invalid/", FakeProcess(), "expected")


def test_failed_start_cleans_only_spawned_children_and_preserves_receipt(tmp_path, monkeypatch):
    sys.path.insert(0, str(runner.ROOT / "backend"))
    from agent_desk import chart_gallery
    monkeypatch.setattr(chart_gallery, "load_gallery", lambda *args: {"entries": [{}], "timings": {}})
    # Only dependency/source identities are fake here; no chart is fabricated.
    root = tmp_path / "repo"
    for rel in ["frontend/node_modules/vite/bin/vite.js", "tools/nova_charts.py",
                "tools/nova_chart_export.mjs", "tools/nova_chart_runner.py", "tools/nova_chart_processes.py",
                "frontend/vite.chart-gateway.config.ts"]:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "__file__", str(root / "tools/nova_chart_runner.py"))
    monkeypatch.setattr(runner.shutil, "which", lambda name: "node")
    monkeypatch.setattr(runner, "_gateway_bundle", lambda node, vite: root / "frontend/.chart-gateway-build/fixture")
    children = []
    class Owner:
        errors = []
        active_processes = 0
        def spawn(self, *args):
            children.append(FakeProcess())
            return children[-1]
        def close(self):
            for child in children:
                child.stopped = True
            return True
    monkeypatch.setattr(runner, "OwnedProcesses", Owner)
    monkeypatch.setattr(runner, "_ready", lambda *args: (_ for _ in ()).throw(TimeoutError("fixture startup timeout")))
    output = tmp_path / "failed"
    with pytest.raises(TimeoutError, match="fixture"):
        runner.export_charts(tmp_path / "selection.json", "0" * 64, output)
    receipt = json.loads((output / "EXPORT_RECEIPT.json").read_text(encoding="utf-8"))
    assert len(children) == 2 and all(child.stopped for child in children)
    assert receipt["ok"] is False and receipt["owned_children_stopped"] is True
    assert receipt["error_type"] == "TimeoutError"


def fake_frontend(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    for rel in ["frontend/src/chart/gateway/main.tsx", "frontend/chart-gateway.html",
                "frontend/vite.chart-gateway.config.ts", "frontend/package-lock.json"]:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", root)
    builds = []

    def build(args, **kwargs):
        out = Path(args[args.index("--outDir") + 1])
        out.mkdir(parents=True)
        (out / "chart-gateway.html").write_text("<html></html>", encoding="utf-8")
        builds.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(runner.subprocess, "run", build)
    return root, builds


def test_renderer_bundle_builds_once_and_is_reused(tmp_path, monkeypatch):
    root, builds = fake_frontend(tmp_path, monkeypatch)
    first = runner._gateway_bundle("node", root / "vite.js")
    assert (first / "chart-gateway.html").is_file() and len(builds) == 1
    assert "build" in builds[0] and "vite.chart-gateway.config.ts" in builds[0]
    assert runner._gateway_bundle("node", root / "vite.js") == first and len(builds) == 1


def test_a_changed_frontend_source_rebuilds_and_drops_the_old_bundle(tmp_path, monkeypatch):
    root, builds = fake_frontend(tmp_path, monkeypatch)
    first = runner._gateway_bundle("node", root / "vite.js")
    (root / "frontend/src/chart/gateway/main.tsx").write_text("changed source", encoding="utf-8")
    second = runner._gateway_bundle("node", root / "vite.js")
    assert second != first and len(builds) == 2
    assert not first.exists() and second.is_dir()


def test_a_failed_build_leaves_no_bundle(tmp_path, monkeypatch):
    root, _ = fake_frontend(tmp_path, monkeypatch)
    monkeypatch.setattr(runner.subprocess, "run",
                        lambda args, **kw: subprocess.CompletedProcess(args, 1, "", "build error"))
    with pytest.raises(RuntimeError, match="renderer build failed"):
        runner._gateway_bundle("node", root / "vite.js")
    assert not any((root / "frontend/.chart-gateway-build").glob("*/chart-gateway.html"))
