"""Playhead-first acquisition: coverage as ranges, seek, clip, backfill (historical-replay.md).

The operator drags the replay ahead of the download. The download must follow:
fetch at the playhead next, keep going forward, and fill the skipped stretch
afterwards -- without ever storing a print twice, reading prints out of time
order, or drawing an undownloaded stretch as a quiet one.
"""
import asyncio
import threading

import pytest

import l2.db as l2_db
from sim import history_coverage as coverage
from sim import history_download, history_playback as playback, history_store as store
from sim import session_clock as clock
from sim.history_download import run


# ---------------------------------------------------------------------------
# Pure range arithmetic


def test_ranges_merge_touching_and_overlapping_spans():
    assert coverage.normalize([[10, 20], [20, 30], [5, 8], [7, 9], [40, 40]]) == [[5, 9], [10, 30]]
    assert coverage.add([[0, 10]], 10, 15) == [[0, 15]]


def test_membership_is_half_open():
    ranges = [[0, 10], [20, 30]]
    assert coverage.contains(ranges, 0) and coverage.contains(ranges, 9)
    assert not coverage.contains(ranges, 10) and not coverage.contains(ranges, 15)
    assert coverage.covers(ranges, 20, 30) and not coverage.covers(ranges, 5, 25)


def test_next_fetch_goes_forward_then_wraps_to_backfill():
    start, end = 0, 100
    ranges = [[0, 20], [50, 100]]
    assert coverage.next_fetch(ranges, 55, start, end) == 20   # past the end -> first gap
    assert coverage.next_fetch(ranges, 25, start, end) == 25   # already in a gap
    assert coverage.next_fetch([[0, 100]], 0, start, end) is None
    assert coverage.next_covered_start(ranges, 25) == 50


def test_a_job_saved_before_ranges_reads_as_its_contiguous_prefix():
    assert coverage.job_ranges({"start_ts": 0, "cursor": 40}) == [[0, 40]]
    assert coverage.job_ranges({"start_ts": 0, "cursor": 0}) == []
    assert coverage.job_ranges({"start_ts": 0, "cursor": 40, "ranges": [[60, 70]]}) == [[60, 70]]
    assert coverage.contiguous_through([[0, 40], [60, 70]], 0) == 40
    assert coverage.contiguous_through([[60, 70]], 0) == 0


# ---------------------------------------------------------------------------
# Store + worker


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setattr(l2_db, "cache_dir", lambda: tmp_path)
    l2_db.init_db()
    clock.reset_for_tests()
    playback.clear()
    yield
    clock.reset_for_tests()
    playback.clear()


@pytest.fixture
def job():
    spec = store.window("IMCC", "2026-09-18", "09:15", "09:25")  # 600 seconds
    created = store.create(spec, "trades")
    store.update(created["id"], status="running")
    return store.get(created["id"])


class Market:
    """IBKR-shaped historical ticks: pages of `size` from any start, final second completed."""

    def __init__(self, job, size=3, every=10):
        self.prints = [dict(ts=t, price=5.0 + (t - job["start_ts"]) / 1000, size=100,
                            symbol="IMCC", exchange="NSDQ", conditions="")
                       for t in range(job["start_ts"], job["end_ts"] + 60, every)]
        self.size, self.calls = size, []

    async def open(self, symbol):
        return {"conId": 1}

    async def trades(self, cursor):
        self.calls.append(cursor)
        ahead = [p for p in self.prints if p["ts"] >= cursor]
        page = ahead[:self.size]
        return page + [p for p in ahead[self.size:] if page and p["ts"] == page[-1]["ts"]]

    def close(self):
        pass


def test_a_seek_moves_the_next_fetch_to_the_playhead(job):
    target = job["start_ts"] + 400
    store.request_seek(job["id"], target)
    moved = store.apply_seek(job["id"])
    assert moved["cursor"] == target and moved["seek"] is None


def test_a_seek_to_downloaded_data_outside_the_window_or_a_stopped_job_does_nothing(job):
    store.commit_page(job["id"], job["cursor"], [], job["start_ts"] + 100)
    assert store.request_seek(job["id"], job["start_ts"] + 50).get("seek") is None     # covered
    assert store.request_seek(job["id"], job["end_ts"] + 5).get("seek") is None        # outside
    store.update(job["id"], status="paused")
    assert store.request_seek(job["id"], job["start_ts"] + 400).get("seek") is None    # not running


def test_a_page_stops_at_downloaded_data_and_never_stores_a_print_twice(job):
    s = job["start_ts"]
    # Already downloaded [s+300, s+600) -- e.g. after an earlier jump ahead.
    store.update(job["id"], ranges=[[s + 300, s + 600]])
    rows = [dict(ts=s + t, price=5, size=1) for t in (0, 150, 299, 300, 350)]
    committed = store.commit_page(job["id"], s, rows, s + 351)
    assert committed["count"] == 3                          # 300 and 350 were already held
    assert committed["ranges"] == [[s, s + 600]]            # merged, so...
    assert committed["status"] == "complete"                # ...the window is whole


def test_reaching_the_window_end_wraps_to_backfill_the_skipped_gap(job):
    s, e = job["start_ts"], job["end_ts"]
    store.request_seek(job["id"], s + 400)
    store.apply_seek(job["id"])
    done_ahead = store.commit_page(job["id"], s + 400, [], e)
    assert done_ahead["status"] == "running"
    assert done_ahead["cursor"] == s                        # back to fill [s, s+400)
    assert done_ahead["ranges"] == [[s + 400, e]]


def test_worker_follows_a_seek_then_backfills_to_a_complete_ordered_window(job):
    s, e = job["start_ts"], job["end_ts"]
    market = Market(job)
    store.request_seek(job["id"], s + 400)
    result = asyncio.run(run(job["id"], market, threading.Event(), paced=False))
    assert market.calls[0] == s + 400                      # the playhead first
    assert result["status"] == "complete" and result["ranges"] == [[s, e]]
    prints = store.read_prints(job["id"])
    stamps = [p["ts"] for p in prints]
    assert stamps == sorted(stamps)                         # time order despite the jump
    assert stamps == [p["ts"] for p in market.prints if p["ts"] < e]   # every print, once
    assert len({p["seq"] for p in prints}) == len(prints)  # stable identities


def test_pausing_drops_a_pending_seek(job):
    store.request_seek(job["id"], job["start_ts"] + 400)
    store.update(job["id"], status="pause_requested")
    result = asyncio.run(run(job["id"], Market(job), threading.Event(), paced=False))
    assert result["status"] == "paused" and result.get("seek") is None


# ---------------------------------------------------------------------------
# Playback over a gap


def select_with_gap(job):
    """Downloaded [s, s+60) and [s+300, s+360); the stretch between is a gap."""
    s = job["start_ts"]
    store.update(job["id"], ranges=[[s + 300, s + 360]], cursor=s)
    store.commit_page(job["id"], s, [dict(ts=s + 10, price=5.0, size=100),
                                     dict(ts=s + 50, price=5.1, size=100)], s + 60)
    later = store.get(job["id"])
    with store.connect() as db:                           # prints for the later range
        for i, (t, price) in enumerate([(310, 6.0), (320, 6.2), (350, 6.1)]):
            db.execute("INSERT INTO prints VALUES (?,?,?,?)",
                       (job["id"], later["count"] + i, s + t,
                        f'{{"ts": {s + t}, "price": {price}, "size": 100}}'))
    store.update(job["id"], count=later["count"] + 3)
    playback.select({k: job[k] for k in ("symbol", "date", "start", "end", "start_ts",
                                         "end_ts", "timezone", "source")})
    clock.set_paused(True)
    return s


def test_the_tape_is_empty_in_a_gap_and_never_spans_one(job):
    s = select_with_gap(job)
    clock.scrub_to_second(200)                            # s+200: in the gap
    gap = playback.snapshot("IMCC")
    assert gap["covered"] is False and gap["prints"] == []
    assert gap["source"] == "mixed"                       # trades exist, just not here
    clock.scrub_to_second(330)                            # s+330: in the later range
    later = playback.snapshot("IMCC")
    assert later["covered"] is True
    assert [p["ts"] for p in later["prints"]] == [s + 320, s + 310]   # this range only
    assert later["selection"]["coverage"] == [[s, s + 60], [s + 300, s + 360]]


def test_candles_are_never_flat_filled_across_a_gap(job):
    s = select_with_gap(job)
    clock.scrub_to_second(420)
    bars = playback.bars("IMCC", "1Min", 100, clock.now_et())
    minutes = {int(bars_store_ts(b)) - s for b in bars}
    # Built from the first range (0) and the whole-minute bucket of the later
    # range (300); the gap minutes 60-240 stay empty with no archive bars.
    assert 0 in minutes and 300 in minutes
    assert not minutes & {60, 120, 180, 240}


def bars_store_ts(bar):
    from sim.history_cache import timestamp
    return timestamp(bar)


def test_a_committed_scrub_points_the_running_download_at_the_playhead(job):
    s = select_with_gap(job)
    store.update(job["id"], status="running")
    clock.scrub_to_second(200)                            # into the gap
    history_download.follow_playhead(clock.now_et().timestamp())
    assert store.get(job["id"])["seek"] == s + 200
