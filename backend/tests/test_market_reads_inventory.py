"""The bulk index build's bookkeeping (``research/market_reads/inventory.py``, 2026-10-12): an index that was not
saved counts as a failure, so ``tools/market_data.py index`` never reports "0 failed" for a day still read the slow way."""
from __future__ import annotations

import gzip
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import inventory  # noqa: E402
from sim import massive_index  # noqa: E402

pytestmark = pytest.mark.skipif(not massive_index.available(), reason="indexed_gzip is not installed")


@pytest.fixture
def day_file(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    path = tmp_path / "trades_v1" / "2026" / "09" / "2026-09-18.csv.gz"
    path.parent.mkdir(parents=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write("ticker,price\nAA,1\nAAPL,2\n")
    return path


def test_a_built_index_is_built(day_file):
    assert inventory._build_one(str(day_file), 1 << 20)[1] == "built"
    assert inventory._build_one(str(day_file), 1 << 20)[1] == "current"


def test_an_index_that_was_not_saved_is_a_failure(day_file, monkeypatch):
    monkeypatch.setattr(massive_index, "_save", lambda *a, **k: None)      # a full disk or a read-only folder
    with pytest.raises(RuntimeError, match="not saved"):
        inventory._build_one(str(day_file), 1 << 20)


def test_a_file_another_build_holds_is_skipped(day_file, monkeypatch):
    lock = massive_index.path_for(day_file, day_file.parents[3])
    lock = lock.with_name(lock.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("1")
    assert inventory._build_one(str(day_file), 1 << 20)[1].startswith("skipped")


def test_a_task_after_stop_returns_at_once(day_file):
    stop = day_file.parents[3] / "sim" / "index" / inventory.INDEX_STOP
    stop.parent.mkdir(parents=True, exist_ok=True)
    stop.write_text("")
    assert inventory._build_one(str(day_file), 1 << 20)[1] == inventory.STOPPED
    assert not massive_index.is_current(day_file, day_file.parents[3])


RUN_STOPPED_BUILD = """
import sys, threading
from pathlib import Path
sys.path[:0] = [{research!r}, {backend!r}]
from market_reads import inventory

if __name__ == "__main__":
    stop = Path({root!r}) / "sim" / "index" / inventory.INDEX_STOP
    threading.Timer(0.5, lambda: (stop.parent.mkdir(parents=True, exist_ok=True), stop.write_text(""))).start()
    print("failed", inventory.build_indexes(["trades_v1"], workers=2, read_mb=1), flush=True)
"""


def test_a_bulk_build_stopped_part_way_ends(tmp_path):
    """2026-10-12: cancelling the pool's queue on STOP left a task already handed out unrun, and the run waited on it
    forever (with no workers). Each task now checks STOP itself, so the run always ends. Run in its own process,
    killed with its pool at the deadline, so a hang fails this test instead of hanging the suite."""
    import os
    import signal
    import subprocess

    root = tmp_path / "massive"
    for i in range(1, 21):
        path = root / "trades_v1" / "2026" / "09" / f"2026-09-{i:02d}.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", newline="") as fh:
            fh.write("ticker,price\nAA,1\nAAPL,2\n")
    here = Path(__file__).resolve().parents[2]
    script = tmp_path / "run_stopped_build.py"
    script.write_text(RUN_STOPPED_BUILD.format(research=str(here / "research"), backend=str(here / "backend"),
                                               root=str(root)), encoding="utf-8")
    # Its own process group, so the deadline kills the build and its pool with the OS's own tools (CI has no psutil).
    group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True,
                            env={**os.environ, "NOVA_MARKET_DATA_DIR": str(root)}, **group)
    try:
        out, _ = proc.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        pytest.fail("the stopped bulk build did not end within 120 s")
    assert proc.returncode == 0 and "failed 0" in out
    log = (root / "sim" / "index" / inventory.INDEX_LOG).read_text(encoding="utf-8")
    assert "index: stopped with" in log or "index: finished" in log
