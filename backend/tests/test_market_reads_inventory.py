"""The bulk index build's bookkeeping (``research/market_reads/inventory.py``, 2026-10-12): an index that was not
saved counts as a failure, so ``tools/market_data.py index`` never reports "0 failed" for a day still read the slow way."""
from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import inventory  # noqa: E402
from sim import massive_index  # noqa: E402

pytestmark = pytest.mark.skipif(not massive_index.available(), reason="indexed_gzip is not installed")


@pytest.fixture(autouse=True)
def _pytest_keeps_its_priority(monkeypatch):
    """``_build_one`` and ``build_indexes`` lower their own process below normal. Called here in-process, that process
    is pytest's for the rest of the run, and Windows passes the class on to every child it starts: a busy PC then
    starves the whole suite (#1079)."""
    monkeypatch.setattr(inventory, "below_normal", lambda: None)


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
import sys, threading, time
from pathlib import Path
sys.path[:0] = [{research!r}, {backend!r}]
from market_reads import inventory

# Normal priority, the test's own: below normal, a busy PC starves the build outright (#1079: one worker start took
# 147 s with every core busy), and what is tested here is the stop, not the build's yielding to the desk. At the top
# level, so each pool worker (which runs this file as __mp_main__) gets it too.
inventory.below_normal = lambda: None
STOP_PART_WAY = {stop_part_way!r}


def stop_after_the_first_build(index):
    # On the run's own progress, not a timer: a timer could fire before the run clears an old STOP (#1079).
    log = index / inventory.INDEX_LOG
    while not (log.exists() and " built in " in log.read_text(encoding="utf-8")):
        time.sleep(0.01)
    (index / inventory.INDEX_STOP).write_text("")


if __name__ == "__main__":
    index = Path({root!r}) / "sim" / "index"
    if STOP_PART_WAY:
        threading.Thread(target=stop_after_the_first_build, args=(index,), daemon=True).start()
    stage = Path({stage!r}) if {stage!r} else None
    # No memory floor: the build would wait up to RAM_WAIT_SEC for this PC's free memory (#1079); that wait has
    # its own tests below.
    print("failed", inventory.build_indexes(["trades_v1"], workers=2, read_mb=1, stage=stage, stage_gb=1e-6,
                                            ram_floor_gb=0.0), flush=True)
"""
BUILD_FILES = 20
BUILD_DEADLINE_FLOOR_SEC = 60.0
WORKER_START_MARGIN = 3.0          # the deadline allows each file's worker start three times what one takes now
# The build and its probe run at normal priority, whatever class pytest runs at (Windows hands it down to children).
_NORMAL_PRIORITY = getattr(subprocess, "NORMAL_PRIORITY_CLASS", 0)


def _worker_start_sec(here: Path) -> float:
    """One cold start of a build worker on this machine, now: a fresh process importing the build, as the pool starts
    one per file (``max_tasks_per_child=1``). A busy PC slows it (#1079)."""
    import time

    code = f"import sys; sys.path[:0] = [{str(here / 'research')!r}]; from market_reads import inventory"
    t0 = time.monotonic()
    subprocess.run([sys.executable, "-c", code], check=True, creationflags=_NORMAL_PRIORITY)
    return time.monotonic() - t0


def build_deadline_sec(worker_start_sec: float, files: int = BUILD_FILES) -> float:
    """The deadline a bulk build of ``files`` gets: sized from what one worker start costs on this machine now, so a
    loaded PC gets the time its load needs and a hang still fails."""
    return BUILD_DEADLINE_FLOOR_SEC + WORKER_START_MARGIN * files * worker_start_sec


def test_the_build_deadline_grows_with_the_machine_s_load():
    assert build_deadline_sec(0.5) == 90.0
    assert build_deadline_sec(10.0) > 120.0 > build_deadline_sec(0.5)   # 120 s, the old fixed deadline


def _run_build(tmp_path, *, stop_part_way, stage):
    """The bulk build in its own process, killed with its pool at the deadline, so a hang fails the test instead of
    hanging the suite. Returns the Massive root."""
    import os
    import signal

    root = tmp_path / "massive"
    for i in range(1, BUILD_FILES + 1):
        path = root / "trades_v1" / "2026" / "09" / f"2026-09-{i:02d}.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", newline="") as fh:
            fh.write("ticker,price\nAA,1\nAAPL,2\n")
    here = Path(__file__).resolve().parents[2]
    script = tmp_path / "run_build.py"
    script.write_text(RUN_BUILD.format(research=str(here / "research"), backend=str(here / "backend"),
                                       root=str(root), stop_part_way=stop_part_way, stage=str(stage) if stage else ""),
                      encoding="utf-8")
    deadline = build_deadline_sec(_worker_start_sec(here))
    # Its own process group, so the deadline kills the build and its pool with the OS's own tools (CI has no psutil).
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | _NORMAL_PRIORITY} if os.name == "nt"
             else {"start_new_session": True})
    proc = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True,
                            env={**os.environ, "NOVA_MARKET_DATA_DIR": str(root)}, **group)
    try:
        out, _ = proc.communicate(timeout=deadline)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        pytest.fail(f"the bulk build did not end within {deadline:.0f} s")
    assert proc.returncode == 0 and "failed 0" in out
    return root


@pytest.mark.parametrize("staged", [False, True])
def test_a_bulk_build_stopped_part_way_ends(tmp_path, staged):
    """2026-10-12: cancelling the pool's queue on STOP left a task already handed out unrun, and the run waited on it
    forever (with no workers). Each task now checks STOP itself, so the run always ends; a staged run stops copying
    too, and leaves no copy behind."""
    stage = tmp_path / "stage" if staged else None
    root = _run_build(tmp_path, stop_part_way=True, stage=stage)
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
    root = _run_build(tmp_path, stop_part_way=False, stage=stage)
    assert all(massive_index.is_current(path, root) for path in inventory.day_files("trades_v1"))
    assert not list(left.iterdir())
    assert "index: finished, 0 failed" in (root / "sim" / "index" / inventory.INDEX_LOG).read_text(encoding="utf-8")
    status = json.loads((root / "sim" / "index" / index_watch.STATUS_FILE).read_text(encoding="utf-8"))
    assert status["state"] == "finished" and status["built"] == 20 and status["failed"] == 0


# ---- the watchdog (index_watch, 2026-10-13: 191 failures and a run short of memory, seen by nobody) ------------
from market_reads import index_watch  # noqa: E402


@pytest.fixture(autouse=True)
def _no_notifications(monkeypatch):
    monkeypatch.setenv(index_watch.ALERTS_ENV, "0")


def _watch(tmp_path, streak_halt=3):
    stop = tmp_path / inventory.INDEX_STOP
    return index_watch.Watch(tmp_path, stop, files=10, total_bytes=10 * 10**9, workers=2,
                             streak_halt=streak_halt), stop


def test_failures_in_a_row_halt_the_run_and_say_why(tmp_path, monkeypatch):
    alerts = []
    monkeypatch.setattr(index_watch, "alert", lambda title, body: alerts.append(title))
    watch, stop = _watch(tmp_path)
    watch.failed("ZranError: zran_init returned error")
    assert not watch.halted.is_set() and alerts == ["Nova index build: a day file failed"]   # the first, at once
    watch.built("a", 10**9, 1e8, 60)                                                        # a success resets it
    for _ in range(3):
        watch.failed("ZranError: zran_init returned error")
    assert watch.halted.is_set() and stop.exists() and "3 builds failed in a row" in stop.read_text(encoding="utf-8")
    assert alerts[-1] == "Nova index build halted"
    status = index_watch.read_status(tmp_path)
    assert status["state"] == "running" and status["failed"] == 4 and "in a row" in status["reason"]
    watch.finish("halted", 6)
    assert index_watch.read_status(tmp_path)["state"] == "halted"


def test_a_run_whose_process_is_gone_reads_as_died(tmp_path):
    watch, _ = _watch(tmp_path)
    path = tmp_path / index_watch.STATUS_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    data["pid"] = 2**22 + 7                                   # no such process
    path.write_text(json.dumps(data), encoding="utf-8")
    status = index_watch.read_status(tmp_path)
    assert status["state"] == "died" and "no stop or finish recorded" in status["reason"]


def test_an_unknown_status_schema_is_said_not_read(tmp_path):
    (tmp_path / index_watch.STATUS_FILE).write_text(json.dumps({"schema_version": 99, "state": "running"}))
    assert index_watch.read_status(tmp_path)["state"] == "unreadable"


def test_a_build_without_free_memory_never_starts(day_file, monkeypatch):
    monkeypatch.setattr(index_watch, "wait_for_ram", lambda *a: False)
    assert inventory._build_one(str(day_file), 1 << 20)[1] == inventory.LOW_RAM
    assert not massive_index.is_current(day_file, day_file.parents[3])


def test_waiting_for_memory_ends_on_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(index_watch, "free_ram", lambda: 1)
    monkeypatch.setattr(index_watch, "RAM_POLL_SEC", 0.01)
    stop = tmp_path / "STOP"
    assert index_watch.wait_for_ram(3.0, 0.05, stop) is False
    stop.write_text("")
    assert index_watch.wait_for_ram(3.0, 10.0, stop) is True


def test_free_memory_is_read_on_this_os():
    free = index_watch.free_ram()
    assert free is None or free > 0


def test_a_run_that_cannot_go_on_is_a_failure_and_a_halt(tmp_path, monkeypatch):
    """A full stage or a broken pool (``_Stager.broke``): counted, named, halted -- never a "0 failed" finish."""
    alerts = []
    monkeypatch.setattr(index_watch, "alert", lambda title, body: alerts.append(title))
    watch, stop = _watch(tmp_path)
    watch.run_failed("could not copy x to y ([Errno 28] No space left on device)")
    watch.finish("halted", 3)
    status = index_watch.read_status(tmp_path)
    assert status["state"] == "halted" and status["failed"] == 1 and "No space" in status["reason"]
    assert alerts == ["Nova index build halted"] and stop.exists()


def test_a_low_memory_halt_exits_nonzero(tmp_path, monkeypatch):
    """A run halted for memory has no failed build, but its command must not report success."""
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    path = tmp_path / "trades_v1" / "2026" / "09" / "2026-09-18.csv.gz"
    path.parent.mkdir(parents=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write("ticker,price\nAA,1\n")
    assert inventory.build_indexes(["trades_v1"], workers=1, read_mb=1, ram_floor_gb=1e9, ram_wait_sec=0.0) == 1
    status = index_watch.read_status(tmp_path / "sim" / "index")
    assert status["state"] == "halted" and "memory free" in status["reason"]
