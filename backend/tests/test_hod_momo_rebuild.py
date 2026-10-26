"""A rebuilt day's HOD Momo alerts (ADR 023 amendment 2026-10-14).

A small day in Massive's own file format and a rebuilt leaderboard day: the real engine, fed the L1 ticks IBKR
would have sent for the stocks HOD Momo would have watched, raises the day's alerts -- and never writes the live
desk's HOD files while it does.
"""
from __future__ import annotations

import gzip
import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from constants_hod_momo import (
    HOD_MOMO_ACTIVE_SET_CAPACITY,
    HOD_MOMO_REBUILD_FLOAT_BASIS,
    HOD_MOMO_REBUILD_L1_TICK_SEC,
    HOD_MOMO_STRATEGY_DEFAULTS,
)
from constants_leaderboard import (
    LEADERBOARD_BOARD_GAPPERS,
    LEADERBOARD_BOARD_MARKET,
    LEADERBOARD_SOURCE_RECONSTRUCTED,
    LEADERBOARD_STATE_REBUILT,
)
from day_movers import floats as mover_floats, store as movers
from hod_momo_rebuild import batch, daily, engine, job, playback, run, store, ticks, watch
from leaderboard import store as board_store
from leaderboard.rows import make_row
from sim import massive_daily, massive_days

ET = ZoneInfo("America/New_York")
DAY, PRIOR, OLDER = "2026-09-18", "2026-09-17", "2026-09-16"
TRADES = "ticker,conditions,correction,exchange,id,participant_timestamp,price,sequence_number,sip_timestamp,size,tape,trf_id,trf_timestamp"
BARS = "ticker,volume,open,close,high,low,window_start,transactions"


def ts(hms: str, day: str = DAY) -> int:
    return int(datetime.fromisoformat(f"{day}T{hms}").replace(tzinfo=ET).timestamp())


def _trade(ticker, hms, ms, price, size, *, seq, conds="", corr=0):
    ns = ts(hms) * 10**9 + ms * 10**6
    return f"{ticker},{conds},{corr},12,{seq},{ns},{price},{seq},{ns},{size},3,0,0"


def _day_bar(ticker, day, open_, high, volume):
    return f"{ticker},{volume},{open_},{open_},{high},{open_},{ts('09:30:00', day) * 10**9},1"


def _write(root, dataset, day, header, lines):
    path = root / dataset / day[:4] / day[5:7] / f"{day}.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", newline="") as fh:
        fh.write(header + "\n" + "\n".join(lines) + "\n")


# AAA runs from 2.00 to 2.60 between 07:40 and 07:45 on 50,000-share prints: a new high of day every print.
RAMP = [(f"07:{40 + i // 6}:{(i % 6) * 10:02d}", round(2.0 + i * 0.02, 2)) for i in range(31)]
DAY_TRADES = [_trade("AAA", hms, 0, price, 50_000, seq=i + 1) for i, (hms, price) in enumerate(RAMP)]


def _row(symbol, hms, board, rank, price, prev):
    return {**make_row(symbol=symbol, minute_ts=ts(hms), board=board, source=LEADERBOARD_SOURCE_RECONSTRUCTED,
                       rank=rank, price=price, prev_close=prev, volume=100_000),
            "session_date": DAY}


def _stored_day():
    rows = []
    for minute in range(39, 47):
        hms = f"07:{minute:02d}"
        rows.append(_row("AAA", hms, LEADERBOARD_BOARD_MARKET, 1, 2.0, 1.0))
        rows.append(_row("AAA", hms, LEADERBOARD_BOARD_GAPPERS, 1, 2.0, 1.0))
    coverage = [{"session_date": DAY, "minute_ts": ts("07:40"), "source": LEADERBOARD_SOURCE_RECONSTRUCTED,
                 "board": LEADERBOARD_BOARD_MARKET, "state": LEADERBOARD_STATE_REBUILT, "row_count": 1, "run_id": None}]
    with board_store.connect() as db:
        board_store.write_batch(db, rows=rows, coverage=coverage)


def _sec_counts():
    """The movers store's SEC share counts: AAA's 2,000,000 was filed the day before; the 50,000,000 filed on the
    day itself was not on file at the open. BBB's only count was filed on the day. CCC's 30,000,000 filed before
    the day is on the old share basis of a 1-for-10 reverse split executing on the day."""
    with movers.connect() as db:
        movers.replace_sec_shares(db, [
            {"symbol": "AAA", "cik": "1", "as_of": OLDER, "filed": PRIOR, "shares": 2_000_000, "form": "10-Q"},
            {"symbol": "AAA", "cik": "1", "as_of": PRIOR, "filed": DAY, "shares": 50_000_000, "form": "8-K"},
            {"symbol": "BBB", "cik": "2", "as_of": OLDER, "filed": DAY, "shares": 1_000_000, "form": "10-Q"},
            {"symbol": "CCC", "cik": "3", "as_of": OLDER, "filed": PRIOR, "shares": 30_000_000, "form": "10-Q"},
        ])
        movers.replace_splits(db, [{"symbol": "CCC", "execution_date": DAY, "split_from": 10, "split_to": 1}])


@pytest.fixture
def day(tmp_path, monkeypatch):
    root = tmp_path / "massive"
    monkeypatch.setenv("NOVA_MARKET_DATA_DIR", str(root))
    monkeypatch.setattr(job, "launch", job._launch_thread)
    massive_daily.reset_for_tests()
    massive_days.reset_for_tests()
    _write(root, "trades_v1", DAY, TRADES, DAY_TRADES)
    _write(root, "minute_aggs_v1", DAY, BARS, [])
    _write(root, "day_aggs_v1", DAY, BARS, [_day_bar("AAA", DAY, 2.40, 2.60, 1_550_000)])
    _write(root, "day_aggs_v1", PRIOR, BARS, [_day_bar("AAA", PRIOR, 1.0, 1.1, 10_000)])
    _write(root, "day_aggs_v1", OLDER, BARS, [_day_bar("AAA", OLDER, 9.0, 9.5, 2_000)])
    reference = root / "store" / "reference"
    reference.mkdir(parents=True)
    (reference / "tickers.json").write_text(json.dumps([{"ticker": "AAA", "type": "CS"}]), encoding="utf-8")
    # A 10-for-1 split after OLDER (from 1 to 10): its 9.50 high reads 0.95 and its 2,000 shares 20,000 on the day
    (reference / "splits.json").write_text(json.dumps([
        {"ticker": "AAA", "execution_date": PRIOR, "split_from": 1, "split_to": 10}]), encoding="utf-8")
    _sec_counts()
    _stored_day()
    yield root
    job.reset_for_tests()
    playback.reset_for_tests()
    massive_daily.reset_for_tests()


def _wait(until=("ready", "failed", "stopped"), timeout=60.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = job.status(DAY)
        if state.get("status") in until:
            return state
        time.sleep(0.05)
    raise AssertionError(f"rebuild of {DAY} still {job.status(DAY)}")


# ── L1 ticks ────────────────────────────────────────────────────────────────

def _ns(sec: float) -> int:
    return int(round(sec * 1e9))


def test_ticks_conflate_like_an_l1_line_and_count_every_trade():
    m = ts("07:40")
    prints = [
        (_ns(m + 0.05), 1, 2.00, 100, True),
        (_ns(m + 0.10), 2, 2.10, 100, True),     # same interval: only its last price is delivered
        (_ns(m + 0.12), 3, 2.50, 7, False),      # an odd lot: volume, never the price or the high
        (_ns(m + 0.30), 4, 2.05, 100, True),
        (_ns(m + 61.0), 5, 3.00, 100, True),     # the next minute: no line, no tick -- but the day's counters run
        (_ns(m + 120.4), 6, 2.90, 100, True),
    ]
    day = ticks.build("AAA", prints, [m, m + 120])
    step = HOD_MOMO_REBUILD_L1_TICK_SEC
    assert list(day.ts) == [m + step, m + 2 * step, m + 120 + 2 * step]
    assert list(day.price) == [2.10, 2.05, 2.90]
    assert list(day.volume) == [207, 307, 507]
    assert list(day.high) == [2.10, 2.10, 3.00]
    assert day.prints == 6
    assert [b[0] for b in day.bars] == [m, m + 60, m + 120]
    assert day.bars[0][1:5] == (2.00, 2.10, 2.00, 2.05)


# ── Who is watched ──────────────────────────────────────────────────────────

def test_the_watch_set_is_the_live_active_set_over_each_minutes_boards():
    m = ts("07:40")
    gainers = [{"symbol": f"G{i:02d}", "rank": i + 1, "change_pct": 1.0 - i / 100} for i in range(50)]
    plan = watch.WatchPlan(boards={m: {LEADERBOARD_BOARD_MARKET: gainers,
                                       LEADERBOARD_BOARD_GAPPERS: [{"symbol": "GAP", "rank": 1, "change_pct": 0.2}]}})
    minutes = plan.active_minutes()
    assert len(minutes) == HOD_MOMO_ACTIVE_SET_CAPACITY
    assert "GAP" in minutes and "G00" in minutes and "G49" not in minutes


# ── What it knows ───────────────────────────────────────────────────────────

def test_day_facts_are_as_of_the_day_and_split_adjusted(day):
    facts = daily.history(DAY, ["AAA", "ZZZ"])
    aaa = facts["AAA"]
    assert aaa.avg_volume == pytest.approx((10_000 + 20_000) / 2)
    assert aaa.fifty_two_week_high == pytest.approx(1.1)          # never the day's own 2.60
    assert aaa.day_open == pytest.approx(2.40)
    assert facts["ZZZ"].avg_volume is None and facts["ZZZ"].fifty_two_week_high is None


def test_the_float_is_the_sec_count_filed_before_the_day_never_a_later_one(day):
    floats = daily.floats(DAY, ["AAA", "BBB", "CCC", "ZZZ"])
    assert floats["AAA"]["float_shares"] == 2_000_000          # not the 50,000,000 filed during the day
    assert floats["AAA"]["shares_outstanding"] == 2_000_000 and floats["AAA"]["filed"] == PRIOR
    assert floats["AAA"]["float_contradicted"] is None
    assert floats["BBB"]["float_shares"] is None               # its only count came the day itself: unknown
    assert floats["CCC"]["float_shares"] == 3_000_000          # on the day's basis: the reverse split that day
    assert floats["ZZZ"]["float_shares"] is None
    # The day-movers default still counts a filing made that day; the rebuild asks for what was known at the open.
    with movers.connect() as db:
        assert mover_floats.sec_shares(db, [(DAY, "AAA")])[(DAY, "AAA")]["shares"] == 50_000_000
        assert mover_floats.sec_shares(db, [(DAY, "AAA")], before=True)[(DAY, "AAA")]["shares"] == 2_000_000


def test_without_a_movers_store_every_float_is_unknown(day, tmp_path):
    assert daily.floats(DAY, ["AAA"], tmp_path / "none.sqlite3")["AAA"]["float_shares"] is None


# ── The build ───────────────────────────────────────────────────────────────

def _hod_files():
    root = os.environ["NOVA_CACHE_DIR"]
    return sorted(name for _dir, _sub, names in os.walk(root) for name in names if "hod" in name.lower())


def test_the_real_engine_raises_the_days_alerts_and_writes_none_of_the_live_files(day):
    before = _hod_files()
    summary = run.run(DAY)
    assert _hod_files() == before
    data = store.read_data(DAY)
    assert summary["watched"] == 1 and summary["ticks"] == len(RAMP)
    assert summary["pending_unflushed"] == 0          # the last burst went out at its end, as the live loop sends it
    assert data["float_basis"] == HOD_MOMO_REBUILD_FLOAT_BASIS == "sec_outstanding_prior_day"
    floors = {sid for sid, cfg in HOD_MOMO_STRATEGY_DEFAULTS.items()
              if cfg.get("min_float") and cfg.get("enabled", True)}
    assert floors and set(summary["floor_unproven"]) == floors     # an upper bound never proves a floor
    alerts = data["alerts"]
    assert alerts, summary
    assert {a["ticker"] for a in alerts} == {"AAA"}
    created = [a["created_ts"] for a in alerts]
    assert created == sorted(created)
    assert ts("07:40") <= created[0] and created[-1] <= ts("07:46")
    assert all(a["float_shares"] == 2_000_000 and a["rvol_source"] == "ibkr_pace" for a in alerts)
    assert not {a["strategy_id"] for a in alerts} & floors
    assert all(a["change_pct"] and a["change_pct"] >= 100 for a in alerts)    # from the 1.00 prior close
    assert all(a["gap_pct"] is None for a in alerts)                          # premarket: no open yet


def test_saves_and_the_writer_threads_hand_offs_are_off_inside_and_restored_after(day):
    import cache
    import hod_momo_writer

    originals = {name: getattr(hod_momo_writer, name) for name in ("submit", "submit_alerts", "submit_highs")}
    original = cache.save_hod_momo_highs
    with engine.no_saves():
        assert cache.save_hod_momo_highs is not original
        for name, fn in originals.items():
            assert getattr(hod_momo_writer, name) is not fn
        hod_momo_writer.submit_highs(DAY, {"session_highs": {"AAA": 9.0}})      # queues nothing
    assert cache.save_hod_momo_highs is original
    assert {name: getattr(hod_momo_writer, name) for name in originals} == originals
    assert hod_momo_writer.drain()
    assert _hod_files() == []


# ── The job and the route ───────────────────────────────────────────────────

def _client():
    from routes.hod_momo import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_asking_builds_it_and_the_history_serves_it_as_rebuilt(day):
    client = _client()
    first = client.get(f"/api/hod-momo/history/{DAY}").json()
    assert first["recorded"] is False and first["source"] is None and first["alerts"] == []
    assert first["rebuild"]["status"] == "none"
    assert client.post(f"/api/hod-momo/history/{DAY}/rebuild").json()["status"] == "queued"
    assert _wait()["status"] == "ready"
    body = client.get(f"/api/hod-momo/history/{DAY}").json()
    assert body["source"] == "rebuilt" and body["alerts"]
    assert body["rebuild"]["float_basis"] == "sec_outstanding_prior_day"
    early = client.get(f"/api/hod-momo/history/{DAY}", params={"until": ts("07:39:59")}).json()
    assert early["source"] == "rebuilt" and early["alerts"] == []
    # Ready and current: asking again starts nothing.
    assert job.request(DAY)["status"] == "ready"


def test_a_change_to_the_hod_settings_makes_the_build_out_of_date(day, monkeypatch):
    job.request(DAY)
    assert _wait()["status"] == "ready"
    monkeypatch.setattr(engine, "config_digest", lambda: "other settings")
    assert job.status(DAY) == {"status": "none", "reason": job.STALE}
    assert playback.answer(DAY)["alerts"] == []


def test_a_day_without_files_reads_unavailable_so_the_desk_never_asks(day):
    body = _client().get("/api/hod-momo/history/2026-09-15").json()
    assert body["rebuild"]["status"] == "unavailable" and "not on disk" in body["rebuild"]["reason"]


def test_a_recorded_day_and_a_day_without_files_are_never_rebuilt(day):
    import cache

    cache.save_hod_momo_snapshot_for_date(DAY, [], time.time())
    assert job.request(DAY) == {"status": "unavailable", "reason": job.RECORDED}
    assert job.request("2026-09-15")["status"] == "unavailable"


def test_only_a_calendar_day_ever_names_a_file_or_the_workers_command(day):
    assert store.day_key("2026-09-18") == "2026-09-18"
    for junk in ("../../etc", "2026-02-30", "2026-9-18x", "latest", "2026-09-18/../x"):
        with pytest.raises(ValueError):
            store.data_path(junk)
    assert job.worker_command("2026-09-18")[-1] == "2026-09-18"
    client = _client()
    assert client.post("/api/hod-momo/history/2026-02-30/rebuild").json()["status"] == "unavailable"
    assert client.get("/api/hod-momo/history/2026-02-30").json() == {}


# ── Many days in a row ──────────────────────────────────────────────────────

class _Ended:
    def __init__(self, code: int):
        self.code = code

    def poll(self) -> int:
        return self.code


def _build_here(started: list):
    def launch(day: str) -> _Ended:
        started.append(day)
        run.run(day)
        return _Ended(0)
    return launch


def test_a_batch_builds_what_it_can_and_a_second_run_skips_the_built_days(day):
    # A day built before the float was point in time (logic version 1) is out of date: the batch builds it again.
    store.write_data(DAY, fingerprint="1:old:old", float_basis="yahoo_now", summary={}, alerts=[])
    store.write_job(DAY, status="ready", fingerprint="1:old:old")
    days = batch.days_between("2026-09-15", DAY)
    assert days == [DAY, PRIOR, OLDER, "2026-09-15"]                     # newest first
    started: list[str] = []
    tally = batch.run_batch(days, launch=_build_here(started), poll_sec=0.0)
    assert started == [DAY] and [d for d, _sec in tally.built] == [DAY] and not tally.failed
    assert tally.skipped == {"The day's Massive trades file is not on disk": 3}
    assert store.read_data(DAY)["float_basis"] == "sec_outstanding_prior_day"
    assert job.status(DAY)["status"] == "ready"

    again: list[str] = []
    tally = batch.run_batch(days, launch=_build_here(again), poll_sec=0.0)
    assert again == [] and tally.built == [] and tally.skipped[batch.BUILT] == 1


def test_a_day_with_no_rebuilt_boards_or_being_built_is_skipped(day, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(job, "_boards_mark", lambda day, fresh=False: None)
        tally = batch.run_batch([DAY], launch=_build_here([]), poll_sec=0.0)
    assert tally.skipped == {job.NOT_REBUILT: 1}
    store.write_job(DAY, status="building")
    tally = batch.run_batch([DAY], launch=_build_here([]), poll_sec=0.0)
    assert tally.skipped == {batch.BUSY: 1}


def test_a_worker_that_dies_reads_failed_and_the_batch_goes_on(day):
    tally = batch.run_batch([DAY], launch=lambda d: _Ended(3), poll_sec=0.0)
    assert tally.failed == [DAY]
    assert job.status(DAY)["status"] == "failed" and "exit code 3" in store.read_job(DAY)["error"]


def test_the_job_is_stamped_with_the_wall_clock_while_the_engine_pins_time(day):
    from hod_momo_replay import ReplayClock, pinned_clock

    with pinned_clock(ReplayClock(ts("09:30"))):        # the engine stage: time.time() reads the replayed day
        record = store.write_job(DAY, status="building")
    assert abs(record["updated_ts"] - time.time()) < 60  # so another process can tell a live build from a dead one


def test_a_stop_file_starts_no_further_day_and_is_removed(day):
    batch.folder().mkdir(parents=True, exist_ok=True)
    batch.stop_path().write_text("", encoding="utf-8")
    started: list[str] = []
    tally = batch.run_batch([DAY], launch=_build_here(started), poll_sec=0.0)
    assert tally.stopped and started == [] and not batch.stop_path().exists()
