"""The MCP server's own warm renderer: real processes in a real Job, with a stand-in for the gateway's warm module.

The stand-in ``nova_chart_warm.py`` answers ``status`` / ``stop`` from a state file and runs ``serve`` as a process
that starts one child of its own, so the tests see the Job stop a whole tree. No node, browser or market data.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nova_chart_mcp_warm as mcp_warm  # noqa: E402

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows Job Objects")

STAND_IN = '''
import json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE, STOP, CHILD = HERE / "state.json", HERE / "stop", HERE / "child.pid"


def status():
    try:
        return {"ok": True, "running": True, "pid": json.loads(STATE.read_text())["pid"]}
    except FileNotFoundError:
        return {"ok": True, "running": False}


def stop():
    STOP.write_text("stop")
    deadline = time.monotonic() + 10
    while STATE.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return {"ok": not STATE.exists(), "stopped": True}


if __name__ == "__main__" and sys.argv[1] == "serve":
    idle = int(sys.argv[sys.argv.index("--idle-seconds") + 1])
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    CHILD.write_text(str(child.pid))
    STATE.write_text(json.dumps({"pid": os.getpid()}))
    end = time.monotonic() + idle
    while time.monotonic() < end and not STOP.exists():
        time.sleep(0.05)
    STATE.unlink()
    STOP.unlink(missing_ok=True)
'''


@pytest.fixture
def gateway(tmp_path):
    tools = tmp_path / "gateway" / "tools"
    tools.mkdir(parents=True)
    (tools / "nova_chart_warm.py").write_text(STAND_IN, encoding="utf-8")
    shutil.copy(Path(__file__).with_name("nova_chart_processes.py"), tools)  # the real Job owner
    return tmp_path / "gateway"


def alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


def test_the_server_starts_one_renderer_reuses_it_and_stops_it_verified(gateway):
    renderer = mcp_warm.WarmRenderer(gateway, Path(sys.executable), idle_seconds=60)
    pid = renderer.ensure()
    assert renderer.ensure() == pid, "a running renderer is reused, not started twice"
    child = int((gateway / "tools/child.pid").read_text())
    assert alive(pid) and alive(child)
    report = renderer.close()
    assert report == {"stopped": True, "verified": True, "exit_code": 0, "live_descendants": 0}
    assert not alive(pid) and not alive(child), "the Job stopped the renderer's own children too"


def test_an_idle_renderer_is_reaped_verified_and_a_new_one_started(gateway):
    renderer = mcp_warm.WarmRenderer(gateway, Path(sys.executable), idle_seconds=1)
    first = renderer.ensure()
    deadline = time.monotonic() + 15
    while (gateway / "tools/state.json").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    second = renderer.ensure()
    assert second != first and not alive(first)
    assert renderer.reaped == [{"pid": first, "verified": True, "exit_code": 0}]
    assert renderer.close()["verified"] is True


def test_a_renderer_someone_else_started_is_used_and_left_running(gateway):
    (gateway / "tools/state.json").write_text(json.dumps({"pid": 4242}), encoding="utf-8")
    renderer = mcp_warm.WarmRenderer(gateway, Path(sys.executable))
    assert renderer.ensure() == 4242
    assert renderer.close() == {"stopped": False, "verified": True, "exit_code": None, "live_descendants": 0}
    assert (gateway / "tools/state.json").exists()


def test_a_renderer_that_dies_while_starting_is_reported_not_waited_for(gateway):
    (gateway / "tools/nova_chart_warm.py").write_text(
        STAND_IN.replace('if __name__ == "__main__"', 'if __name__ == "__main__" and False'), encoding="utf-8")
    renderer = mcp_warm.WarmRenderer(gateway, Path(sys.executable))
    began = time.monotonic()
    with pytest.raises(mcp_warm.WarmRendererUnavailable, match="exited"):
        renderer.ensure()
    assert time.monotonic() - began < 15
    assert renderer.close()["verified"] is True


def test_idle_seconds_are_bounded(gateway):
    for value in (0, 3601, True):
        with pytest.raises(ValueError):
            mcp_warm.WarmRenderer(gateway, Path(sys.executable), idle_seconds=value)
