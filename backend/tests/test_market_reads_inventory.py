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


def test_a_bulk_build_stopped_part_way_ends(tmp_path, monkeypatch):
    """2026-10-12: cancelling the pool's queue on STOP left a task already handed out unrun, and the run waited on it
    forever (with no workers). Each task now checks STOP itself, so the run always ends."""
    import threading

    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(tmp_path))
    for i in range(1, 21):
        path = tmp_path / "trades_v1" / "2026" / "09" / f"2026-09-{i:02d}.csv.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", newline="") as fh:
            fh.write("ticker,price\nAA,1\nAAPL,2\n")
    stop = tmp_path / "sim" / "index" / inventory.INDEX_STOP
    threading.Timer(0.5, lambda: (stop.parent.mkdir(parents=True, exist_ok=True), stop.write_text(""))).start()
    done = []
    runner = threading.Thread(target=lambda: done.append(inventory.build_indexes(["trades_v1"], workers=2, read_mb=1)))
    runner.start()
    runner.join(120)
    assert done == [0]                                  # it ended, and nothing failed
    log = (tmp_path / "sim" / "index" / inventory.INDEX_LOG).read_text(encoding="utf-8")
    assert "index: stopped with" in log or "index: finished" in log
