"""Nova's recorded IBKR sessions through the front door (``research/market_reads/recordings.py``, ADR 059, #1064).

Fixture stores only, built in ``tmp_path`` with the desk's own schemas: depth at a moment (best price first, never after
the moment, never across a gap, the newer of two stores), prints in a window (both stores, paged, capped), coverage said
on every answer, and the reads leave the stores exactly as the live desk wrote them."""
from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("pandas")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research"))

from market_reads import recording_files, recording_stores, recordings, roots, slots  # noqa: E402

ET = ZoneInfo("America/New_York")
DAY = "2026-10-14"


def T(clock: str, day: str = DAY) -> float:
    return datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=ET).timestamp()


def book_row(ts, bids, asks, symbol="GRML"):
    return {"symbol": symbol, "ts": ts, "bids": [{"price": p, "size": s} for p, s in bids],
            "asks": [{"price": p, "size": s} for p, s in asks], "source": "ibkr", "session_date": DAY,
            "schema_version": 1}


def print_row(ts, price, size, conditions="", side=None, bid=None, ask=None, symbol="GRML", **more):
    return {"type": "print", "symbol": symbol, "ts": ts, "receive_ts": ts + 0.05, "price": price, "size": size,
            "exchange": "NASDAQ", "conditions": conditions, "unreported": False, "side": side, "bid": bid, "ask": ask,
            "exchange_ts": float(int(ts)), "source": "ibkr", "schema_version": 1, **more}


def write_jsonl(path: Path, rows) -> None:
    path.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows), encoding="utf-8")


def make_record(root: Path, symbol="GRML", day=DAY, l2=(), prints=(), segments=None, **manifest):
    """A Session Record: two segments (09:30-09:40 a restart ended, 09:50-10:00 the operator stopped)."""
    folder = root / day / symbol
    folder.mkdir(parents=True)
    segments = segments if segments is not None else [
        {"started_et": datetime.fromtimestamp(T("09:30:00", day), ET).isoformat(),
         "stopped_et": datetime.fromtimestamp(T("09:40:00", day), ET).isoformat(),
         "status": "stopped_partial_ok", "reason": "restart"},
        {"started_et": datetime.fromtimestamp(T("09:50:00", day), ET).isoformat(),
         "stopped_et": datetime.fromtimestamp(T("10:00:00", day), ET).isoformat(),
         "status": "stopped_partial_ok", "reason": "operator"}]
    body = {"symbol": symbol, "session_date": day, "source": "ibkr", "schema": "sim_capture_v1", "schema_version": 1,
            "status": "stopped_partial_ok", "segments": segments,
            "fidelity": {"l2_offered": 40, "l2_coalesced": 9, "l2_max_hz": 50.0, "tape_resubscribes": 1,
                         "timestamp_regressions": 0,
                         "tape_losses": [{"at": T("09:35:00", day), "cause": "stale", "detail": "quiet"}]}, **manifest}
    (folder / "manifest.json").write_text(json.dumps(body), encoding="utf-8")
    write_jsonl(folder / "l2.jsonl", l2)
    write_jsonl(folder / "prints.jsonl", prints)
    end = T("10:00:05", day)
    for stream in folder.glob("*.jsonl"):          # the recorder's last write: the open-segment rule reads mtimes
        os.utime(stream, (end, end))
    return folder


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """Fixture Session Records, ``l2.db`` and ``archive.db`` -- the desk's own DDL, never the operator's stores."""
    from archive import db as archive_db
    from l2 import db as l2_db

    cap, cache = tmp_path / "sim_capture", tmp_path / "cache"
    cap.mkdir()
    cache.mkdir()
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(cap))
    monkeypatch.setenv("NOVA_CACHE_DIR", str(cache))
    for name, ddl in (("l2.db", l2_db._SCHEMA), ("archive.db", archive_db._SCHEMA)):
        db = sqlite3.connect(cache / name)
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(ddl)
        db.commit()
        db.close()
    return {"cap": cap, "cache": cache}


def l2_insert(cache: Path, rows) -> None:
    db = sqlite3.connect(cache / "l2.db")
    db.executemany("INSERT INTO l2_snapshots (recording_id, symbol, setup, signal_ts, ts, bids_json, asks_json, "
                   "l1_fallback, session_id) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    db.commit()
    db.close()


def snap(ts, bids, asks, symbol="GRML", fallback=0, session="GRML:depth:abc"):
    return ("rec", symbol, "continuous", ts, ts, json.dumps([{"price": p, "size": s} for p, s in bids]),
            json.dumps([{"price": p, "size": s} for p, s in asks]), fallback, session)


def tape_insert(cache: Path, rows) -> None:
    db = sqlite3.connect(cache / "archive.db")
    db.executemany("INSERT INTO tape_ibkr (symbol, ts, price, size, exchange, conditions, side, bid, ask, seq, "
                   "receive_ts, source, session_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.commit()
    db.close()


def trow(ts, price, size, conditions="", side=None, symbol="GRML", bid=None, ask=None):
    return (symbol, ts, price, size, "NASDAQ", conditions, side, bid, ask, None, ts + 0.04, "ibkr", DAY)


# ---------------------------------------------------------------- the jsonl search

def test_a_stream_is_searched_by_offset_and_matches_a_full_scan(tmp_path):
    base = T("04:00:00")
    rows = [{"symbol": "X", "ts": base + i * 0.5, "n": i, "pad": "x" * 60} for i in range(30_000)]
    path = tmp_path / "prints.jsonl"
    write_jsonl(path, rows)
    assert path.stat().st_size > 20 * recording_files.BLOCK            # big enough that the bisect really runs
    rng = random.Random(7)
    for at in [base - 10, base, base + 0.4, base + 14_999.5, base + 99_999] + [base + rng.uniform(0, 15_000) for _ in range(60)]:
        want = [r for r in rows if r["ts"] <= at]
        got = recording_files.newest_at_or_before(path, at, "X")
        assert (got["n"] if got else None) == (want[-1]["n"] if want else None), at
    for lo, hi in [(base + 100.2, base + 130.7), (base - 5, base + 3), (base + 14_990, base + 20_000), (base + 50, base + 50)]:
        got, capped = recording_files.rows_between(path, lo, hi, 10_000, "X")
        assert [r["n"] for r in got] == [r["n"] for r in rows if lo <= r["ts"] < hi] and not capped
    got, capped = recording_files.rows_between(path, base, base + 1000, 7, "X")
    assert len(got) == 7 and capped


def test_a_line_the_recorder_is_still_writing_is_skipped(tmp_path):
    path = tmp_path / "l2.jsonl"
    path.write_bytes(b'{"ts": 1700000000.0, "n": 1}\n{"ts": 1700000001.0, "n": 2}\n{"ts": 17000000')   # torn tail
    assert recording_files.newest_at_or_before(path, 1700000009.0)["n"] == 2
    assert [r["n"] for r in recording_files.rows_between(path, 0, 1700000099.0, 10)[0]] == [1, 2]
    assert recording_files.newest_at_or_before(tmp_path / "none.jsonl", 1.0) is None


# ---------------------------------------------------------------- depth

def test_a_book_is_best_price_first_and_never_from_after_the_moment(stores):
    make_record(stores["cap"], l2=[book_row(T("09:31:00"), [(1.00, 100), (1.02, 200)], [(1.05, 300), (1.03, 50)]),
                                   book_row(T("09:32:00"), [(1.10, 10)], [(1.12, 20)])])
    answer = recordings.depth("grml", DAY, "09:31:30", source="capture")
    book = answer["book"]
    assert answer["covered"] and answer["source"] == "capture"
    assert [lv["price"] for lv in book["bids"]] == [1.02, 1.00] and [lv["price"] for lv in book["asks"]] == [1.03, 1.05]
    assert (book["best_bid"], book["best_ask"], book["spread"], book["mid"]) == (1.02, 1.03, 0.01, 1.025)
    assert book["time_et"] == "09:31:00.000" and book["age_sec"] == 30.0 and book["bid_levels"] == 2
    assert answer["at_et"].startswith(f"{DAY}T09:31:30") and "-04:00" in answer["at_et"]
    # at the instant of a book it is that book; a moment before the first book has none
    assert recordings.depth("GRML", DAY, "09:32:00", source="capture")["book"]["best_bid"] == 1.10
    early = recordings.depth("GRML", DAY, "09:30:10", source="capture")
    assert early["covered"] is False and "no book at or before" in early["reason"]


def test_a_book_is_never_read_across_a_gap(stores):
    make_record(stores["cap"], l2=[book_row(T("09:39:00"), [(2.00, 5)], [(2.05, 5)])])
    inside = recordings.depth("GRML", DAY, "09:39:30", source="capture")
    assert inside["covered"] and inside["book"]["age_sec"] == 30.0
    gap = recordings.depth("GRML", DAY, "09:45:00", max_age_sec=3600, source="capture")     # 09:40-09:50 was not recorded
    assert gap["covered"] is False and "gap" in gap["reason"]
    cap = gap["coverage"]["capture"]
    assert cap["at_in_stretch"] is False and cap["gaps"][0]["reason"] == "restart" and cap["gaps"][0]["planned"] is False
    assert [s["reason"] for s in cap["stretches"]] == ["restart", "operator"]
    # inside the second stretch the book from before the gap is not reachable either
    after = recordings.depth("GRML", DAY, "09:50:30", max_age_sec=3600, source="capture")
    assert after["covered"] is False and "before the gap" in after["reason"]


def test_a_book_older_than_max_age_is_not_served_and_the_coverage_is_stated(stores):
    make_record(stores["cap"], l2=[book_row(T("09:31:00"), [(1.00, 1)], [(1.01, 1)])])
    stale = recordings.depth("GRML", DAY, "09:33:00", source="capture")                 # 120 s, max_age 60
    assert stale["covered"] is False and "max_age_sec" in stale["reason"]
    assert recordings.depth("GRML", DAY, "09:33:00", max_age_sec=300, source="capture")["covered"]
    fid = stale["coverage"]["capture"]["fidelity"]
    assert fid["l2_offered"] == 40 and fid["l2_coalesced"] == 9 and fid["l2_max_hz"] == 50.0
    assert fid["tape_losses"] == [{"at_et": f"{DAY}T09:35:00-04:00", "cause": "stale"}]


def test_auto_serves_the_newer_store_and_a_tie_goes_to_the_capture(stores):
    make_record(stores["cap"], l2=[book_row(T("09:31:00"), [(1.00, 1)], [(1.01, 1)])])
    l2_insert(stores["cache"], [snap(T("09:31:20"), [(1.50, 9)], [(1.51, 9)]),
                                snap(T("09:31:40"), [(1.70, 9)], [(1.71, 9)], fallback=1)])   # top of book only: skipped
    answer = recordings.depth("GRML", DAY, "09:31:30")
    assert answer["source"] == "l2_db" and answer["book"]["best_bid"] == 1.50 and answer["book"]["session_id"]
    assert [t["source"] for t in answer["tried"]] == ["capture", "l2_db"] and all(t["covered"] for t in answer["tried"])
    assert answer["tried"][0]["age_sec"] == 30.0 and answer["tried"][1]["age_sec"] == 10.0
    l2_insert(stores["cache"], [snap(T("09:31:00"), [(1.40, 9)], [(1.41, 9)])])
    assert recordings.depth("GRML", DAY, "09:31:10", max_age_sec=15)["source"] == "capture"   # same second: capture


def test_l2_db_says_when_it_sampled_and_never_serves_a_fallback_as_depth(stores):
    l2_insert(stores["cache"], [snap(T("10:00:00"), [(3.0, 1)], [(3.1, 1)]), snap(T("10:30:00"), [(3.2, 1)], [(3.3, 1)]),
                                snap(T("10:15:00"), [(9.9, 1)], [(9.9, 1)], fallback=1)])
    db = sqlite3.connect(stores["cache"] / "l2.db")
    db.execute("INSERT INTO record_sessions VALUES ('GRML:depth:abc','GRML','depth','flat_top',NULL,?,?)",
               (T("09:59:00"), T("10:31:00")))
    db.commit()
    db.close()
    answer = recordings.depth("GRML", DAY, "10:16:00", source="l2_db", max_age_sec=3600)
    assert answer["book"]["best_bid"] == 3.0                            # not the 10:15 fallback row
    cov = answer["coverage"]["l2_db"]
    assert cov["first_et"].endswith("10:00:00-04:00") and cov["last_et"].endswith("10:30:00-04:00")
    assert cov["sessions"] == [{"session_id": "GRML:depth:abc", "reason": "depth", "setup": "flat_top",
                                "started_et": f"{DAY}T09:59:00-04:00", "ended_et": f"{DAY}T10:31:00-04:00"}]


def test_an_unrecorded_moment_is_a_stated_absence_that_says_what_is_recorded(stores):
    make_record(stores["cap"], day="2026-10-13", l2=[book_row(T("09:31:00", "2026-10-13"), [(1, 1)], [(2, 1)])])
    answer = recordings.depth("GRML", DAY, "09:31:00")
    assert answer["covered"] is False and answer["book"] is None and answer["source"] is None
    assert "no Session Record of GRML on 2026-10-14" in answer["reason"] and "l2_db:" in answer["reason"]
    assert answer["recorded_days"]["capture"] == ["2026-10-13"] and answer["recorded_days"]["l2_db"] == []
    assert answer["coverage"]["capture"]["recorded"] is False


def test_a_synthetic_sim1_directory_is_not_a_recording(stores):
    make_record(stores["cap"], l2=[book_row(T("09:31:00"), [(1, 1)], [(2, 1)])], source="sim")
    answer = recordings.depth("GRML", DAY, "09:31:10", source="capture")
    assert answer["covered"] is False and "SIM1" in answer["reason"]


def test_depth_arguments_are_checked(stores):
    for bad in (dict(at="25:00"), dict(at="9"), dict(at="09:61"), dict(source="ibkr"), dict(max_age_sec=0),
                dict(max_age_sec=99_999)):
        with pytest.raises(ValueError):
            recordings.depth("GRML", DAY, **{"at": "09:31", **bad})
    with pytest.raises(ValueError, match="symbol"):
        recordings.depth(" ", DAY, "09:31")
    with pytest.raises(ValueError):
        recordings.depth("GRML", "2026-13-01", "09:31")


# ---------------------------------------------------------------- tape

def test_a_session_record_tape_window_is_et_oldest_first_and_flags_what_sets_a_price(stores):
    make_record(stores["cap"], prints=[
        print_row(T("09:31:00.250"), 1.00, 100, side="ask", bid=0.99, ask=1.00),
        print_row(T("09:31:01.000"), 0.60, 5, conditions="4 W"),               # average-price: volume only
        print_row(T("09:31:02.000"), 1.01, 200, sets_price=True, side="between", bid=1.00, ask=1.02),
        print_row(T("09:41:00.000"), 9.99, 1)])                                # outside the window
    frame = recordings.tape("GRML", DAY, "09:31", "09:32")
    assert list(frame.columns) == recordings.TAPE_COLUMNS and list(frame["source"]) == ["capture"] * 3
    assert list(frame["time_et"]) == ["09:31:00.250", "09:31:01.000", "09:31:02.000"]
    assert list(frame["price"]) == [1.00, 0.60, 1.01] and list(frame["sets_price"]) == [True, False, True]
    assert [None if x != x else x for x in frame["side"]] == ["ask", None, "between"]     # a missing side is null, not NaN
    assert frame["exchange_ts"].iloc[0] == float(int(T("09:31:00.250")))
    assert frame.attrs["source"] == "capture" and frame.attrs["capped"] is False
    assert frame.attrs["window_et"][0].endswith("09:31:00-04:00") and "arrival" in frame.attrs["rules"]
    assert frame.attrs["coverage"]["covered_share"] == 1.0 and frame.attrs["coverage"]["gaps"][0]["reason"] == "restart"
    assert "gaps" in frame.attrs["note"]                                       # the archive may hold what the gap lost
    half = recordings.tape("GRML", DAY, "09:35", "09:45", source="capture")
    assert half.attrs["coverage"]["covered_share"] == 0.5 and list(half["price"]) == [9.99]


def test_without_a_session_record_the_archive_serves_the_tape_and_says_what_it_cannot(stores):
    tape_insert(stores["cache"], [trow(T("09:31:00"), 1.0, 100, side="ask", bid=0.99, ask=1.0),
                                  trow(T("09:31:01"), 0.6, 5, conditions="4 W"), trow(T("09:31:01"), 1.1, 9),
                                  trow(T("11:00:00"), 2.0, 1), trow(T("09:31:05"), 7.0, 1, symbol="OTHER")])
    db = sqlite3.connect(stores["cache"] / "archive.db")
    db.execute("INSERT INTO integrity_counters VALUES ('tape_dropped', 12, 0)")
    db.commit()
    db.close()
    frame = recordings.tape("GRML", DAY, "09:30", "10:00")
    assert frame.attrs["source"] == "archive" and list(frame["price"]) == [1.0, 0.6, 1.1]
    assert list(frame["source"]) == ["archive"] * 3 and frame["exchange_ts"].isna().all() and frame["unreported"].isna().all()
    assert list(frame["sets_price"]) == [True, False, True]                    # judged from the conditions alone
    cov = frame.attrs["coverage"]
    assert cov["dropped_total"] == 12 and cov["first_et"].endswith("09:31:00-04:00") and cov["last_et"].endswith("09:31:01-04:00")
    assert "no gap of its own" in cov["gaps"]
    whole = recordings.tape("GRML", DAY)                                       # the whole ET day
    assert len(whole) == 4 and recordings.tape("grml", DAY, source="archive").equals(whole)


def test_the_archive_is_paged_without_losing_or_repeating_a_print_that_shares_a_second(stores, monkeypatch):
    monkeypatch.setattr(recording_stores, "CHUNK_ROWS", 3)
    rows = [trow(T("09:31:00") + (i // 4), 1.0 + i / 100, 10 + i) for i in range(25)]      # four prints a second
    tape_insert(stores["cache"], rows)
    frame = recordings.tape("GRML", DAY, source="archive")
    assert list(frame["size"]) == [10 + i for i in range(25)]
    capped = recordings.tape("GRML", DAY, source="archive", limit=7)
    assert list(capped["size"]) == [10 + i for i in range(7)] and capped.attrs["capped"] is True
    exact = recordings.tape("GRML", DAY, source="archive", limit=25)
    assert len(exact) == 25 and exact.attrs["capped"] is False


def test_an_empty_window_lists_the_days_that_are_recorded(stores):
    tape_insert(stores["cache"], [trow(T("09:31:00", "2026-10-09"), 1.0, 1), trow(T("09:31:00", "2026-10-12"), 1.0, 1)])
    frame = recordings.tape("GRML", DAY, "09:30", "10:00")
    assert frame.empty and frame.attrs["recorded_days"] == {"archive": ["2026-10-12", "2026-10-09"]}
    assert list(frame.columns) == recordings.TAPE_COLUMNS
    gone = recordings.tape("GRML", DAY, source="capture")
    assert gone.empty and "no Session Record" in gone.attrs["note"]


def test_a_session_record_without_prints_hands_auto_to_the_archive(stores):
    make_record(stores["cap"], l2=[book_row(T("09:31:00"), [(1, 1)], [(2, 1)])], prints=[])
    tape_insert(stores["cache"], [trow(T("09:31:01"), 1.0, 7)])
    frame = recordings.tape("GRML", DAY, "09:31", "09:32")
    assert frame.attrs["source"] == "archive" and list(frame["size"]) == [7]


def test_a_symbol_or_day_that_names_a_path_is_refused_before_the_disk(stores):
    for bad in ("..", "../GRML", "C:\\x", "GR ML"):
        with pytest.raises(ValueError):
            recordings.depth(bad, DAY, "09:31", source="capture")
        with pytest.raises(ValueError):
            recordings.tape(bad, DAY, source="capture")
    with pytest.raises(ValueError):
        recordings.depth("GRML", "../../etc", "09:31", source="capture")


def test_a_missing_cache_says_where_it_looked_and_tape_arguments_are_checked(stores, tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path / "nowhere"))
    frame = recordings.tape("GRML", DAY, source="archive")
    assert frame.empty and "archive.db is not on disk" in frame.attrs["note"] and "NOVA_CACHE_DIR" in frame.attrs["note"]
    for bad in (dict(source="l2_db"), dict(limit=0), dict(limit=10_000_000), dict(start="10:00", end="09:00"),
                dict(start="9am")):
        with pytest.raises(ValueError):
            recordings.tape("GRML", DAY, **bad)


# ---------------------------------------------------------------- never disturb the live desk

def fingerprint(folder: Path):
    """Every file's size and hash. A WAL database opened read-only while no writer has it open gets SQLite's own empty
    ``-wal`` / ``-shm`` side files (the reader protocol: no content of the store); they are checked empty, not hashed."""
    for side in folder.glob("*.db-wal"):
        assert side.stat().st_size == 0, f"{side.name} holds frames a research read wrote"
    return sorted((p.name, p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()) for p in folder.rglob("*")
                  if p.is_file() and not p.name.endswith(("-wal", "-shm")))


def test_reads_leave_every_store_exactly_as_the_desk_wrote_it(stores):
    make_record(stores["cap"], l2=[book_row(T("09:31:00"), [(1, 1)], [(2, 1)])], prints=[print_row(T("09:31:01"), 1, 1)])
    l2_insert(stores["cache"], [snap(T("09:31:00"), [(1, 1)], [(2, 1)])])
    tape_insert(stores["cache"], [trow(T("09:31:01"), 1.0, 1)])
    before = {k: fingerprint(v) for k, v in stores.items()}
    recordings.depth("GRML", DAY, "09:31:30")
    recordings.tape("GRML", DAY, "09:31", "09:32")
    recordings.tape("GRML", DAY, "09:31", "09:32", source="archive")
    assert {k: fingerprint(v) for k, v in stores.items()} == before


def test_the_connection_cannot_write(stores):
    with recording_stores.connect(stores["cache"] / "archive.db") as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM tape_ibkr")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE x (a)")
    with pytest.raises(LookupError, match="not on disk"):
        with recording_stores.connect(stores["cache"] / "never.db"):
            pass
    assert not (stores["cache"] / "never.db").exists()                       # connect never makes a store


def test_a_busy_writer_is_not_blocked_and_no_read_lock_outlives_a_read(stores):
    tape_insert(stores["cache"], [trow(T("09:31:00") + i, 1.0, i + 1) for i in range(20)])
    writer = sqlite3.connect(stores["cache"] / "archive.db", isolation_level=None)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("BEGIN IMMEDIATE")                                          # the desk is mid-batch
    writer.execute("INSERT INTO tape_ibkr (symbol, ts, price, size, source, session_date) "
                   "VALUES ('GRML', ?, 9, 9, 'ibkr', ?)", (T("09:31:05"), DAY))
    frame = recordings.tape("GRML", DAY, source="archive")                     # reads the committed rows, never waits
    assert len(frame) == 20
    writer.execute("COMMIT")
    assert len(recordings.tape("GRML", DAY, source="archive")) == 21
    busy, _log, _ckpt = writer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    assert busy == 0                                                           # no reader still holds the WAL back
    writer.close()


def test_every_read_takes_a_heavy_slot(stores, monkeypatch):
    from contextlib import contextmanager
    asked = []

    @contextmanager
    def heavy(what, wait=0):
        asked.append(what)
        yield 0

    monkeypatch.setattr(slots, "heavy", heavy)
    make_record(stores["cap"], l2=[book_row(T("09:31:00"), [(1, 1)], [(2, 1)])])
    recordings.depth("GRML", DAY, "09:31:10")
    recordings.tape("GRML", DAY, "09:31", "09:32")
    assert asked == ["recorded_depth GRML 2026-10-14 09:31:10", "recorded_tape GRML 2026-10-14"]


# ---------------------------------------------------------------- where the stores are

def test_the_cache_is_found_where_the_desk_keeps_it(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVA_CACHE_DIR", raising=False)
    names = [str(p) for p in roots.cache_candidates()]
    assert any(n.endswith(os.path.join("backend", ".cache")) for n in names) and names[-1].lower().startswith("f:")
    monkeypatch.setenv("NOVA_CACHE_DIR", str(tmp_path))
    assert roots.cache_candidates() == [tmp_path]                              # an explicit folder is the only one
    with pytest.raises(LookupError, match="l2.db is not on disk; looked in .*NOVA_CACHE_DIR"):
        roots.cache_store("l2.db")
    (tmp_path / "l2.db").write_bytes(b"")
    assert roots.cache_store("l2.db") == tmp_path / "l2.db"


def test_an_et_day_is_its_own_length_across_a_clock_change():
    for day, hours in (("2026-03-08", 23), ("2026-11-01", 25), ("2026-10-14", 24)):
        _d, lo, hi = recordings._day(day)
        assert (hi - lo) / 3600 == hours
    assert recordings._clock(recordings._day("2026-10-14")[0], "24:00") == recordings._day("2026-10-14")[2]
