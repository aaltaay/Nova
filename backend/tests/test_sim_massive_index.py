"""The Massive day files' seek indexes (ADR 046 amendment, 2026-10-11).

A day file is one gzip stream of every ticker, sorted, with no index: the first read
streams it through zlib, and once the import is done ``massive_index.build`` reads it
start to end through indexed_gzip and saves its seek points and a map of the file; every
later read finds its ticker in the map. These tests hold the indexed read to a whole-file
inflate, row for row, pin when an index is trusted, and keep a build's memory flat.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import subprocess
import sys
import threading
import time
import zlib

import pytest

from sim import history_store, massive_files, massive_import, massive_index, massive_read, massive_store

pytestmark = pytest.mark.skipif(not massive_index.available(), reason="indexed_gzip is not installed")

DAY = "2026-09-18"
HEADER = "ticker,conditions,price,sip_timestamp,size"
TICKERS = ["A", "AA", "AAPL", "BRK.A", "BRK.B", "IMCC", "IMCCW", "IMCD", "VEEA", "ZZZ"]
TRADES = ("ticker,conditions,correction,exchange,id,participant_timestamp,price,sequence_number,sip_timestamp,size,"
          "tape,trf_id,trf_timestamp")


def _lines(tickers, rows_each):
    base = 1_789_740_000 * 10**9
    out = []
    for ticker in tickers:
        for i in range(rows_each(ticker)):
            out.append(f'{ticker},"12,37",{1 + i / 100:.2f},{base + i * 10**6},{100 + i}')
    return out


def _write(root, lines, dataset="trades_v1", *, header=HEADER, newline_at_end=True):
    path = root / dataset / DAY[:4] / DAY[5:7] / f"{DAY}.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write(header + "\n" + "\n".join(lines) + ("\n" if newline_at_end else ""))
    return path


@pytest.fixture
def root(tmp_path, monkeypatch):
    base = tmp_path / "massive"
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(base))
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    return base


def _expected(path, ticker):
    """The reference: the whole file inflated by gzip, every line whose first field is the ticker."""
    lines = gzip.decompress(path.read_bytes()).splitlines()[1:]
    return [line for line in lines if line.split(b",", 1)[0] == ticker.encode()]


def _read(path, ticker, *, indexed):
    with massive_files.DayRead(path, ticker) as read:
        lines = [line for _h, batch in read.batches() for line in batch]
        assert read.indexed is indexed
    return lines


def _built(path, root):
    assert massive_index.build(path, root) == massive_index.path_for(path, root)
    return massive_index.load(path, root)


# ---- the index read equals the whole file's ------------------------------------------------------------------------
@pytest.mark.parametrize("chunk", [7, 64, 150, 333, 1 << 20])
def test_an_indexed_read_returns_exactly_what_the_file_holds(root, monkeypatch, chunk):
    """A mark per stretch read: one per line or so (7, 64 bytes), inside blocks (150, 333), one for the file (1 MB)."""
    monkeypatch.setattr(massive_index, "SIM_MASSIVE_READ_CHUNK", chunk)
    path = _write(root, _lines(TICKERS, lambda t: 1 + len(t) * 7))
    _built(path, root)
    for ticker in TICKERS + ["0", "AAA", "BRK", "IMCB", "IMCCX", "ZZZZ", "~"]:
        assert _read(path, ticker, indexed=True) == _expected(path, ticker), ticker


def test_an_indexed_read_finds_blocks_across_many_seek_points(root, monkeypatch):
    monkeypatch.setattr(massive_index, "SIM_MASSIVE_INDEX_SPACING", 64 * 1024)
    monkeypatch.setattr(massive_index, "SIM_MASSIVE_READ_CHUNK", 16 * 1024)
    names = sorted(f"T{i:05d}" for i in range(4000))
    path = _write(root, _lines(names, lambda t: 1 + int(t[1:]) % 37))
    saved = _built(path, root)
    assert len(saved.marks) > 100 and saved.marks == sorted(saved.marks)
    assert saved.header == HEADER.split(",") and saved.body == len(HEADER) + 1
    for ticker in (names[0], names[1], names[1999], names[2000], names[-2], names[-1], "T00000X", "T99999"):
        assert _read(path, ticker, indexed=True) == _expected(path, ticker), ticker


def test_the_last_line_without_a_newline_is_read_through_the_index(root):
    path = _write(root, _lines(["IMCC", "ZZZ"], lambda t: 3), newline_at_end=False)
    _built(path, root)
    assert len(_read(path, "ZZZ", indexed=True)) == 3 and _read(path, "ZZZ", indexed=True) == _expected(path, "ZZZ")


def test_a_header_longer_than_a_read_is_kept_whole(root, monkeypatch):
    monkeypatch.setattr(massive_index, "SIM_MASSIVE_READ_CHUNK", 5)
    path = _write(root, _lines(TICKERS, lambda t: 2))
    saved = _built(path, root)
    assert saved.header == HEADER.split(",") and saved.body == len(HEADER) + 1


# ---- when an index is written and trusted ---------------------------------------------------------------------------
def test_a_build_asked_to_stop_saves_nothing(root):
    path = _write(root, _lines(TICKERS, lambda t: 5))
    stop = threading.Event()
    stop.set()
    assert massive_index.build(path, root, stop) is None
    assert not massive_index.path_for(path, root).exists()
    assert _read(path, "AAPL", indexed=False) == _expected(path, "AAPL")      # no index: streamed, as always


def test_the_index_file_says_what_it_was_built_from(root):
    path = _write(root, _lines(TICKERS, lambda t: 5))
    _built(path, root)
    where = massive_index.path_for(path, root)
    head = json.loads(where.read_bytes().split(b"\n", 1)[0])
    assert where == root / "sim" / "index" / "trades_v1" / "2026" / "09" / f"{DAY}.csv.gz.idx"
    assert head["schema_version"] == massive_index.SIM_MASSIVE_INDEX_SCHEMA_VERSION
    assert (head["size"], head["mtime_ns"]) == (path.stat().st_size, path.stat().st_mtime_ns)
    assert head["length"] == len(gzip.decompress(path.read_bytes()))
    assert not where.with_name(where.name + ".lock").exists()                # the build let go of its lock


def test_one_build_per_file_and_a_dead_builds_lock_is_taken_over(root):
    path = _write(root, _lines(TICKERS, lambda t: 2))
    where = massive_index.path_for(path, root)
    lock = where.with_name(where.name + ".lock")
    lock.parent.mkdir(parents=True)
    lock.write_text("12345")                                                  # another build, alive
    assert massive_index.build(path, root) is None and not where.exists()
    old = time.time() - massive_index.SIM_MASSIVE_INDEX_LOCK_STALE_SEC - 5   # that build died long ago
    os.utime(lock, (old, old))
    assert massive_index.build(path, root) == where and not lock.exists()


def test_a_day_downloaded_again_is_streamed_and_indexed_again(root):
    path = _write(root, _lines(TICKERS, lambda t: 2))
    _built(path, root)
    path = _write(root, _lines(TICKERS, lambda t: 4))                        # a new copy: size and time differ
    os.utime(path, ns=(time.time_ns(), time.time_ns() + 10**9))
    assert massive_index.load(path, root) is None
    assert len(_read(path, "VEEA", indexed=False)) == 4
    _built(path, root)
    assert len(_read(path, "VEEA", indexed=True)) == 4


def test_an_unknown_or_damaged_index_is_never_read(root, caplog):
    path = _write(root, _lines(TICKERS, lambda t: 2))
    _built(path, root)
    where = massive_index.path_for(path, root)
    head, body = where.read_bytes().split(b"\n", 1)
    future = json.loads(head)
    future["schema_version"] = 99
    where.write_bytes(json.dumps(future).encode() + b"\n" + body)
    with caplog.at_level(logging.WARNING, logger="sim.massive_index"):
        assert massive_index.load(path, root) is None
    assert "schema_version 99" in caplog.text
    where.write_bytes(head + b"\n" + b"not zlib")
    assert massive_index.load(path, root) is None
    shuffled = json.loads(head)
    shuffled["marks"] = [[60, "ZZZ"], [50, "A"]]                              # a map out of the file's order
    where.write_bytes(json.dumps(shuffled).encode() + b"\n" + body)
    assert massive_index.load(path, root) is None
    assert _read(path, "IMCC", indexed=False) == _expected(path, "IMCC")     # the day file still reads, streamed


def test_an_index_that_will_not_open_is_streamed_past_and_rebuilt_by_the_next_import(root, caplog):
    """PR #836 review: a header that checks out over seek points indexed_gzip refuses must not fail the import, every
    time; the read streams the file, and the import builds the index again over the bad one."""
    path = _write(root, _trade_lines(["AAPL", "IMCC", "VEEA", "ZZZ"]), header=TRADES)
    _built(path, root)
    where = massive_index.path_for(path, root)
    head = where.read_bytes().split(b"\n", 1)[0]
    where.write_bytes(head + b"\n" + zlib.compress(b"GZIDX" + bytes(64)))  # zlib-valid, not an index
    assert massive_index.load(path, root) is not None                         # the header passes every check
    with caplog.at_level(logging.WARNING, logger="sim.massive_files"):
        assert _read(path, "VEEA", indexed=False) == _expected(path, "VEEA")
    assert "could not be used" in caplog.text
    assert _import("IMCC")["status"] == "complete"
    assert _read(path, "VEEA", indexed=True) == _expected(path, "VEEA")      # rebuilt over the bad one


def test_without_indexed_gzip_the_files_stream_and_nothing_is_built(root, monkeypatch):
    path = _write(root, _lines(TICKERS, lambda t: 3))
    monkeypatch.setattr(massive_index, "indexed_gzip", None)
    assert _read(path, "IMCD", indexed=False) == _expected(path, "IMCD")
    assert massive_index.build(path, root) is None
    assert not massive_index.path_for(path, root).exists()


def test_a_build_keeps_its_memory_flat(root, monkeypatch):
    """A build holds a fixed amount, whatever the file's size -- never the text it reads (a library that kept its
    text filled the desk PC's memory in testing, 2026-10-11). With 1 MB seek-point spacing and reads the fixed part
    is a few MB, so a build that kept even a fifth of 160 MB of text fails."""
    psutil = pytest.importorskip("psutil")
    monkeypatch.setattr(massive_index, "SIM_MASSIVE_INDEX_SPACING", 2**20)
    monkeypatch.setattr(massive_index, "SIM_MASSIVE_READ_CHUNK", 2**20)
    monkeypatch.setattr(massive_index, "SIM_MASSIVE_INDEX_READBUF", 2**20)
    path = root / "trades_v1" / DAY[:4] / DAY[5:7] / f"{DAY}.csv.gz"
    path.parent.mkdir(parents=True)
    block = b"ABCD,12,0.123456,1789740000000000000,100" + bytes([10])
    with gzip.open(path, "wb", compresslevel=1) as fh:
        fh.write(HEADER.encode() + bytes([10]))
        for i in range(200):                                                  # 200 tickers, 160 MB of text
            fh.write((block * 20_000).replace(b"ABCD", f"T{i:03d}".encode()))
    proc = psutil.Process()
    peak, base = 0, proc.memory_info().rss
    done = threading.Event()

    def watch():
        nonlocal peak
        while not done.wait(0.01):
            peak = max(peak, proc.memory_info().rss - base)
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        saved = _built(path, root)
    finally:
        done.set()
        watcher.join()
    assert saved.length > 150 * 2**20
    assert peak < 32 * 2**20, f"a build of {saved.length / 2**20:.0f} MB of text grew the process by {peak / 2**20:.0f} MB"
    assert _read(path, "T199", indexed=True) == _expected(path, "T199")


# ---- the import -----------------------------------------------------------------------------------------------------
def _trade_lines(tickers):
    base = 1_789_740_000 * 10**9                                              # 2026-09-18 10:00 ET
    return [f"{t},,0,12,1,{base},{1.0 + i},{i},{base + i * 10**9},100,3,0,0" for i, t in enumerate(tickers)]


def _import(symbol):
    spec = massive_import.spec(history_store.window(symbol, DAY, "09:30", "16:00"))
    job = massive_store.save(dict(massive_store.new_job(spec), status="running"))
    return massive_read.run(job["id"])


def test_an_import_builds_the_index_and_the_next_one_reads_through_it(root, caplog):
    path = _write(root, _trade_lines(["AAPL", "IMCC", "VEEA", "ZZZ"]), header=TRADES)
    with caplog.at_level(logging.INFO, logger="sim.massive_read"):
        first = _import("IMCC")
    assert first["status"] == "complete" and first["count"] == 1
    assert massive_index.path_for(path, root).exists()
    assert "read through an index: none" in caplog.text and "Massive index saved for trades_v1" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="sim.massive_read"):
        second = _import("VEEA")
    assert second["status"] == "complete" and second["count"] == 1
    assert "read through an index: trades_v1" in caplog.text and "Massive index saved" not in caplog.text


def _building(job_id):
    """A live import whose job is complete: it only builds indexes now."""
    handle = massive_import._ThreadHandle(job_id)
    handle.thread = threading.Thread(target=handle.event.wait, daemon=True)
    handle.thread.start()
    return handle


def _complete_job(symbol, day=DAY):
    spec = massive_import.spec(history_store.window(symbol, day, "04:00", "20:00"))
    return massive_store.save(dict(massive_store.new_job(spec), status="complete"))


@pytest.mark.parametrize("same_day", [True, False])
def test_an_import_building_indexes_holds_no_slot(root, monkeypatch, same_day):
    """An import of the same day runs beside the build (and reads through the index once it is saved); an import of
    another day ends it, since the day asked for now comes first."""
    monkeypatch.setattr(massive_import, "launch", massive_import._launch_thread)
    _write(root, _trade_lines(["AAPL", "IMCC", "VEEA"]), header=TRADES)
    job = _complete_job("AAPL", DAY if same_day else "2026-09-17")
    handle = _building(job["id"])
    massive_import._active[job["id"]] = handle
    try:
        assert massive_import.running_ids() == [] and massive_import.indexing_ids() == [job["id"]]
        started = massive_import.begin(history_store.window("VEEA", DAY, "09:30", "10:00"))
        assert started["status"] == "running"
        assert job["id"] not in massive_import._active
        assert handle.event.is_set() is (not same_day)
    finally:
        handle.event.set()
        massive_import._active.clear()
        massive_import._indexing.clear()


def test_a_superseded_import_process_never_ends_the_newer_one(root):
    spec = massive_import.spec(history_store.window("IMCC", DAY, "04:00", "20:00"))
    job = massive_store.save(dict(massive_store.new_job(spec), status="running"))
    old = massive_import._ProcessHandle(job["id"], subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]))
    newer = _building(job["id"])
    massive_import._active[job["id"]] = newer                                 # the newer import of this stock-day
    try:
        old.pausing = True
        massive_import._watch(old, None)
        old.proc.terminate()
        old.proc.wait(10)
        time.sleep(0.3)
        assert massive_store.get(job["id"])["status"] == "running"           # not the old process's to pause
    finally:
        newer.event.set()
        massive_import._active.clear()
