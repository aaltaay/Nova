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


def test_a_staged_copy_is_built_as_the_day_file_and_deleted(day_file, tmp_path):
    """``--stage``: the build reads a copy on another drive; the index is the day file's, and the copy is gone."""
    stage = tmp_path / "stage"
    stage.mkdir()
    copy = inventory._copy(day_file, stage)
    assert copy.read_bytes() == day_file.read_bytes() and copy.name == "trades_v1__2026-09-18.csv.gz"
    assert inventory._build_one(str(day_file), 0, str(copy))[1] == "built"
    assert not copy.exists()
    assert massive_index.is_current(day_file, day_file.parents[3])


def test_a_staged_copy_is_deleted_when_the_task_stops(day_file, tmp_path):
    copy = inventory._copy(day_file, tmp_path)
    stop = day_file.parents[3] / "sim" / "index" / inventory.INDEX_STOP
    stop.parent.mkdir(parents=True, exist_ok=True)
    stop.write_text("")
    assert inventory._build_one(str(day_file), 0, str(copy))[1] == inventory.STOPPED
    assert not copy.exists()


RUN_BUILD = """
import sys, threading
from pathlib import Path
sys.path[:0] = [{research!r}, {backend!r}]
from market_reads import inventory

if __name__ == "__main__":
    stop = Path({root!r}) / "sim" / "index" / inventory.INDEX_STOP
    if {stop_after!r} is not None:
        threading.Timer({stop_after!r}, lambda: (stop.parent.mkdir(parents=True, exist_ok=True),
                                                 stop.write_text(""))).start()
    stage = Path({stage!r}) if {stage!r} else None
    print("failed", inventory.build_indexes(["trades_v1"], workers=2, read_mb=1, stage=stage, stage_gb=1e-6),
          flush=True)
"""


def _run_build(tmp_path, *, stop_after, stage):
    """The bulk build in its own process, killed with its pool at the deadline, so a hang fails the test instead of
    hanging the suite. Returns the Massive root."""
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
    script = tmp_path / "run_build.py"
    script.write_text(RUN_BUILD.format(research=str(here / "research"), backend=str(here / "backend"),
                                       root=str(root), stop_after=stop_after, stage=str(stage) if stage else ""),
                      encoding="utf-8")
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
        pytest.fail("the bulk build did not end within 120 s")
    assert proc.returncode == 0 and "failed 0" in out
    return root


@pytest.mark.parametrize("staged", [False, True])
def test_a_bulk_build_stopped_part_way_ends(tmp_path, staged):
    """2026-10-12: cancelling the pool's queue on STOP left a task already handed out unrun, and the run waited on it
    forever (with no workers). Each task now checks STOP itself, so the run always ends; a staged run stops copying
    too, and leaves no copy behind."""
    stage = tmp_path / "stage" if staged else None
    root = _run_build(tmp_path, stop_after=0.5, stage=stage)
    log = (root / "sim" / "index" / inventory.INDEX_LOG).read_text(encoding="utf-8")
    assert "index: stopped with" in log or "index: finished" in log
    if staged:
        assert not list((stage / inventory.STAGE_DIR).iterdir())


def test_a_staged_bulk_build_indexes_every_day_and_leaves_no_copies(tmp_path, monkeypatch):
    """One copy at a time (a budget smaller than a file), each built and deleted, every day indexed."""
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path / "massive"))
    stage = tmp_path / "stage"
    left = stage / inventory.STAGE_DIR
    left.mkdir(parents=True)
    (left / "trades_v1__2026-01-02.csv.gz.part").write_bytes(b"from a run that died")   # cleared at the start
    root = _run_build(tmp_path, stop_after=None, stage=stage)
    assert all(massive_index.is_current(path, root) for path in inventory.day_files("trades_v1"))
    assert not list(left.iterdir())
    assert "index: finished, 0 failed" in (root / "sim" / "index" / inventory.INDEX_LOG).read_text(encoding="utf-8")
