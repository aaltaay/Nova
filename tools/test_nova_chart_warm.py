"""The warm renderer's owner and wire, with a fake driver: no node, browser, broker or market inputs."""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
from multiprocessing import AuthenticationError
from multiprocessing.connection import Listener
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nova_chart_warm as warm  # noqa: E402
import nova_trade_charts as trades  # noqa: E402

windows = pytest.mark.skipif(os.name != "nt", reason="Windows Job Objects and named pipes")
DAY = "2023-05-02"
TRADE = {"symbol": "DEMO", "date": DAY, "entry_time": "07:05:22", "entry_price": 3.39,
         "exit_time": "07:10:20", "exit_price": 4.10}


@pytest.fixture
def builds(tmp_path, monkeypatch):
    monkeypatch.setattr(warm, "BUILDS", tmp_path / "builds")
    monkeypatch.setattr(warm, "STATE", tmp_path / "builds" / ".warm-service.json")
    monkeypatch.setattr(warm, "LOG", tmp_path / "builds" / ".warm-service.log")
    (tmp_path / "builds").mkdir()
    return tmp_path / "builds"


@pytest.mark.parametrize("value", [0, 3601, True, 1.5])
def test_idle_seconds_are_bounded(value):
    with pytest.raises(ValueError):
        warm._idle(value)


def test_an_unknown_rendezvous_schema_is_refused_not_guessed(builds):
    warm.STATE.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    with pytest.raises(warm.WarmUnavailable, match="schema_version"):
        warm.status()


@windows
def test_a_rendezvous_whose_pipe_is_gone_is_a_stopped_service(builds):
    warm.STATE.write_text(json.dumps({"schema_version": 1, "pipe": r"\\.\pipe\nova-chart-warm-gone",
                                      "authkey": "00" * 32}), encoding="utf-8")
    assert warm.status() == {"ok": True, "running": False}
    assert not warm.STATE.exists()


@windows
def test_the_pipe_speaks_json_only_to_the_key_holder(builds):
    key, pipe = os.urandom(32), r"\\.\pipe\nova-chart-warm-test-" + os.urandom(4).hex()
    listener = Listener(pipe, family="AF_PIPE", authkey=key)
    refused = []

    def serve():
        for _ in range(2):
            try:
                with listener.accept() as connection:
                    request = json.loads(connection.recv_bytes())
                    connection.send_bytes(json.dumps({"ok": True, "running": True, "echo": request["op"]}).encode())
            except AuthenticationError:
                refused.append(True)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    warm.STATE.write_text(json.dumps({"schema_version": 1, "pipe": pipe, "authkey": key.hex()}), encoding="utf-8")
    assert warm.status() == {"ok": True, "running": True, "echo": "status"}
    with pytest.raises(AuthenticationError):
        warm._call_raw(pipe, b"wrong key" * 4, {"op": "status"}, 5)
    thread.join(5)
    listener.close()
    assert refused == [True]


def frozen_bundle(tmp_path):
    def read(symbol, day, tf, start, end):
        times = pd.to_datetime([f"{DAY} 07:05:20", f"{DAY} 07:10:20"]).tz_localize("America/New_York")
        return pd.DataFrame({"time_et": times, "open": [3.35, 3.9], "high": [3.4, 4.1], "low": [3.35, 3.9],
                             "close": [3.39, 4.1], "volume": [900, 500], "transactions": [1, 1]})
    massive = tmp_path / "massive"
    (massive / "trades_v1").mkdir(parents=True)
    return trades.resolve_trade_bundle([TRADE], tmp_path / "bundle", massive, read=read)


class FakeDriver:
    """Answers each job the way the Node driver does: the PNGs, the capture verification, one reply line."""

    def __init__(self, service):
        self.service, self.jobs = service, []
        self.stdin = self

    def write(self, data):
        job = json.loads(data)
        self.jobs.append(job)
        images = Path(job["output"])
        images.mkdir(parents=True)
        for name in ("NOVA_HISTORICAL_OVERVIEW.png", "NOVA_GATEWAY_VIEW.png", "01_DEMO_2023-05-02_10s.png"):
            (images / name).write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        (images / "CAPTURE_VERIFICATION.json").write_text(json.dumps({"errors": [], "blocked_requests": []}))
        self.service.replies.put(json.dumps({"id": job["id"], "ok": True}).encode())

    def flush(self):
        pass

    def poll(self):
        return None


@pytest.fixture
def service(tmp_path, monkeypatch):
    if os.name != "nt":
        pytest.skip("OwnedProcesses needs Windows")
    svc = warm._Service(60)
    bundle = tmp_path / "frontend-build" / "key123"
    bundle.mkdir(parents=True)
    (bundle / "chart-gateway.html").write_text("<html></html>")
    svc.bundle, svc.base, svc.instance, svc.page = bundle, "http://127.0.0.1:1", "inst", "http://127.0.0.1:1/p"
    svc.driver = FakeDriver(svc)
    monkeypatch.setattr(warm.runner, "_bundle_key", lambda frontend: "key123")
    yield svc
    svc.owner.close()


def job(receipt, output, **change):
    return dict({"op": "export", "selection": receipt["selection_path"], "sha256": receipt["selection_sha256"],
                 "output": str(output), "samples": 0}, **change)


@windows
def test_a_warm_job_is_checked_drawn_verified_and_says_who_owns_the_renderer(tmp_path, service):
    receipt = frozen_bundle(tmp_path)
    answer = service._export(job(receipt, tmp_path / "bundle" / "images"))
    assert answer["ok"], answer
    native = answer["receipt"]
    assert native["renderer"] == "warm" and native["selection_sha256"] == receipt["selection_sha256"]
    assert native["warm_service"]["pid"] == os.getpid() and native["warm_service"]["jobs_served"] == 1
    assert "owned_trees_stopped" not in native, "a warm receipt never claims its renderer stopped"
    assert native["source_data_mutated"] is False and native["broker_or_desk_calls"] is False
    sent = json.loads(service.driver.jobs[0]["gallery"])
    assert sent["selection_sha256"] == receipt["selection_sha256"] and len(sent["entries"]) == 1
    on_disk = json.loads((tmp_path / "bundle/images/EXPORT_RECEIPT.json").read_text(encoding="utf-8"))
    assert on_disk == native


@windows
def test_changed_renderer_sources_fail_the_job_as_stale_and_stop_the_service(tmp_path, service, monkeypatch):
    receipt = frozen_bundle(tmp_path)
    monkeypatch.setattr(warm.runner, "_bundle_key", lambda frontend: "edited")
    answer = service._export(job(receipt, tmp_path / "bundle" / "images"))
    assert not answer["ok"] and answer["error"].startswith("stale")
    assert service.stopping.is_set()


@windows
def test_existing_output_or_a_wrong_hash_never_reaches_the_driver(tmp_path, service):
    receipt = frozen_bundle(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir()
    assert "Existing output" in service._export(job(receipt, existing))["error"]
    wrong = service._export(job(receipt, tmp_path / "new", sha256="0" * 64))
    assert wrong["error"].startswith("selection refused") and not (tmp_path / "new").exists()
    assert service._export(job(receipt, tmp_path / "new", samples=51))["error"].startswith("samples")
    assert service.driver.jobs == []


def test_the_client_redraws_once_when_the_renderer_was_stale(tmp_path, monkeypatch):
    answers = queue.Queue()
    answers.put({"ok": False, "error": "stale: the renderer or its tools changed"})
    answers.put({"ok": True, "receipt": {"ok": True, "renderer": "warm"}})
    events = []
    monkeypatch.setattr(warm, "start", lambda idle: events.append("start"))
    monkeypatch.setattr(warm, "stop", lambda: events.append("stop"))
    monkeypatch.setattr(warm, "_call", lambda request, timeout: answers.get_nowait())
    output = tmp_path / "images"
    output.mkdir()
    assert warm.export(tmp_path / "selection.json", "0" * 64, output) == {"ok": True, "renderer": "warm"}
    assert events == ["start", "stop", "start"] and not output.exists()


def test_warm_trade_charts_go_through_the_gateways_warm_renderer(tmp_path, monkeypatch):
    import nova_historical_charts as historical
    receipt, calls = frozen_bundle(tmp_path), []

    def fake_export(selection, sha256, output, samples, idle_seconds):
        calls.append((selection, sha256, output, samples, idle_seconds))
        return {"ok": True, "renderer": "warm"}

    monkeypatch.setattr(warm, "export", fake_export)
    monkeypatch.setattr(historical.subprocess, "run", lambda *a, **k: pytest.fail("no one-shot export when warm"))
    result = historical.run_native_export(receipt, warm.ROOT, warm.ROOT / "tools/nova_charts.py", 0, 0.0,
                                          warm_idle_seconds=60)
    assert calls == [(Path(receipt["selection_path"]), receipt["selection_sha256"],
                      tmp_path / "bundle" / "images", 0, 60)]
    written = json.loads((tmp_path / "bundle" / "historical_export.json").read_text(encoding="utf-8"))
    assert written["native_export"]["renderer"] == "warm" and result["ok"] is True


def test_a_failed_warm_job_raises_instead_of_retrying(tmp_path, monkeypatch):
    monkeypatch.setattr(warm, "start", lambda idle: None)
    monkeypatch.setattr(warm, "_call", lambda request, timeout: {"ok": False, "error": "Native export failed: x"})
    with pytest.raises(RuntimeError, match="Native export failed"):
        warm.export(tmp_path / "selection.json", "0" * 64, tmp_path / "images")
