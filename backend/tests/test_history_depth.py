"""Recorded Level 2 reaches historical replay, and absence stays absence (#309).

The operator's decision on #309 was option (b): feed ``l2.db`` into the one
Sim replay surface. These tests pin the honesty half of that -- a book only
appears where one was actually recorded, ``depth_available`` never claims more
than the archive holds, and an unreadable archive costs the replay nothing.
"""
import sqlite3

import pytest

import l2.batch as l2_batch
import l2.db as l2_db
from l2.store import record_snapshot
from sim import history_depth, history_playback as playback, history_store as store
from sim import session_clock as clock

RECORDING = "rec-1"
SETUP = "depth"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setattr(l2_db, "cache_dir", lambda: tmp_path)
    l2_batch.clear_queues_for_tests()
    clock.reset_for_tests()
    playback.clear()
    history_depth.clear()
    yield
    l2_batch.clear_queues_for_tests()
    clock.reset_for_tests()
    playback.clear()
    history_depth.clear()


def book(bid: float, ask: float, size: int = 100) -> dict:
    return {
        "bids": [{"price": bid, "size": size, "side": "bid", "mm": "ISLAND"}],
        "asks": [{"price": ask, "size": size, "side": "ask", "mm": "ARCA"}],
        "l1_fallback": False,
    }


def select(symbol: str = "IMCC") -> dict:
    """A selected window with one print, so the replay itself is live."""
    spec = store.window(symbol, "2026-09-18", "04:00", "09:30")
    job = store.create(spec, "trades")
    store.commit_page(job["id"], spec["start_ts"],
                      [dict(ts=spec["start_ts"], price=10.0, size=100)], spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    return spec


def record_at(spec: dict, offset: float, *, symbol: str = "IMCC", **kwargs) -> None:
    l2_db.init_db()
    record_snapshot(RECORDING, symbol, SETUP, spec["start_ts"],
                    spec["start_ts"] + offset, book(**kwargs) if kwargs else book(9.99, 10.01),
                    session_id="session-1")
    history_depth.clear()


def test_recorded_second_returns_its_book_and_an_unrecorded_one_returns_nothing():
    spec = select()
    record_at(spec, 60)
    clock.scrub_to_second(60)
    found = history_depth.book_at("IMCC", clock.now_et().timestamp())
    assert found is not None
    assert (found["bids"][0]["price"], found["asks"][0]["price"]) == (9.99, 10.01)
    assert found["source"] == "l2_recorder" and found["ts"] == spec["start_ts"] + 60
    clock.scrub_to_second(600)
    assert history_depth.book_at("IMCC", clock.now_et().timestamp()) is None


def test_a_stale_book_never_stands_in_for_an_unrecorded_moment():
    spec = select()
    record_at(spec, 60)
    # Inside the freshness budget the same book still describes the playhead.
    assert history_depth.book_at("IMCC", spec["start_ts"] + 61) is not None
    # Past it, the archive has nothing to say about this second.
    assert history_depth.book_at("IMCC", spec["start_ts"] + 90) is None


def test_the_book_is_never_read_from_ahead_of_the_playhead():
    spec = select()
    record_at(spec, 120)
    assert history_depth.book_at("IMCC", spec["start_ts"] + 60) is None
    assert history_depth.book_at("IMCC", spec["start_ts"] + 120) is not None


def test_another_symbols_recording_is_not_this_replays_book():
    spec = select()
    record_at(spec, 60, symbol="SPY")
    assert history_depth.book_at("IMCC", spec["start_ts"] + 60) is None
    assert history_depth.book_at("SPY", spec["start_ts"] + 60) is not None


def test_snapshot_depth_available_is_true_only_where_a_book_was_recorded():
    spec = select()
    record_at(spec, 60)
    clock.scrub_to_second(60)
    snap = playback.snapshot("IMCC")
    assert snap["depth_available"] is True
    assert snap["depth"]["bids"][0]["price"] == 9.99
    assert snap["depth"]["source"] == "l2_recorder"
    clock.scrub_to_second(600)
    snap = playback.snapshot("IMCC")
    assert snap["depth_available"] is False and snap["depth"] is None
    # A book is not a quote: the download still carries no bid/ask.
    assert snap["bid"] is None and snap["ask"] is None


def test_an_inactive_symbol_claims_no_depth():
    spec = select()
    record_at(spec, 60, symbol="SPY")
    clock.scrub_to_second(60)
    snap = playback.snapshot("SPY")
    assert snap["active"] is False
    assert snap["depth_available"] is False and snap["depth"] is None


def test_a_missing_archive_degrades_and_is_never_created_by_a_replay():
    spec = select()
    clock.scrub_to_second(60)
    snap = playback.snapshot("IMCC")
    assert snap["depth_available"] is False and snap["depth"] is None
    # A desk that never recorded depth keeps having no archive, not an empty one.
    assert not l2_db.db_path().exists()


def test_a_damaged_archive_degrades_instead_of_breaking_the_replay(caplog):
    spec = select()
    record_at(spec, 60)
    l2_db.db_path().write_bytes(b"this is not a database")
    history_depth.clear()
    clock.scrub_to_second(60)
    with caplog.at_level("WARNING"):
        snap = playback.snapshot("IMCC")
    assert snap["depth_available"] is False and snap["depth"] is None
    assert snap["last"] == 10.0  # the replay itself is unharmed
    assert any("Level 2 unavailable" in record.message for record in caplog.records)


def test_a_broken_archive_is_reported_once_per_outage_not_once_per_poll(caplog):
    spec = select()
    record_at(spec, 60)
    l2_db.db_path().write_bytes(b"this is not a database")
    history_depth.clear()
    with caplog.at_level("WARNING"):
        for second in range(60, 66):
            assert history_depth.book_at("IMCC", spec["start_ts"] + second) is None
    warnings = [r for r in caplog.records if "Level 2 unavailable" in r.message]
    assert len(warnings) == 1


def test_repeated_polls_of_one_replayed_second_read_the_archive_once(monkeypatch):
    spec = select()
    record_at(spec, 60)
    reads = []
    real_connect = l2_db.get_connection

    def counted():
        reads.append(1)
        return real_connect()

    monkeypatch.setattr(l2_db, "get_connection", counted)
    import l2.store as l2_store
    monkeypatch.setattr(l2_store, "get_connection", counted)
    clock.scrub_to_second(60)
    for _ in range(5):
        assert playback.snapshot("IMCC")["depth_available"] is True
    assert len(reads) == 1


def test_selecting_a_window_again_picks_up_a_session_recorded_since():
    spec = select()
    clock.scrub_to_second(60)
    assert playback.snapshot("IMCC")["depth_available"] is False
    l2_db.init_db()
    record_snapshot(RECORDING, "IMCC", SETUP, spec["start_ts"], spec["start_ts"] + 60,
                    book(9.98, 10.02), session_id="session-1")
    playback.select(spec)
    assert playback.snapshot("IMCC")["depth"]["bids"][0]["price"] == 9.98


def test_a_locked_archive_does_not_raise_into_the_snapshot(monkeypatch):
    spec = select()
    record_at(spec, 60)

    def locked(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    import l2.store as l2_store
    monkeypatch.setattr(l2_store, "get_connection", locked)
    history_depth.clear()
    clock.scrub_to_second(60)
    snap = playback.snapshot("IMCC")
    assert snap["depth_available"] is False and snap["depth"] is None
