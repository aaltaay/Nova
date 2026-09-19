"""Reached trades, closed-bar fallback and rewind must share one time cut."""
from datetime import datetime

import pytest
import bars_store
from archive import db
from sim import history_playback as playback, history_store as store, session_clock as clock


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    db.init_db()
    clock.reset_for_tests()
    playback.clear()
    yield
    clock.reset_for_tests()
    playback.clear()


def prepare():
    spec = store.window("IMCC", "2026-09-18", "04:00", "09:30")
    job = store.create(spec, "trades")
    a = spec["start_ts"]
    rows = [dict(ts=a + sec, price=price, size=size) for sec, price, size in
            [(0, 10, 2), (0, 10, 2), (30, 11, 3), (60, 20, 7), (80, 99, 100)]]
    store.commit_page(job["id"], a, rows, spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    return spec


def test_reached_volume_identicals_partial_and_rewind():
    prepare()
    clock.scrub_to_second(60)
    now = clock.now_et()
    candles = playback.bars("IMCC", "1Min", 100, now)
    assert [r["v"] for r in candles] == [7, 7]
    assert candles[-1]["h"] == 20 and candles[-1]["partial"]
    snap = playback.snapshot("IMCC")
    assert snap["volume"] == sum(r["v"] for r in candles) == 14
    assert len(snap["prints"]) == 4
    clock.scrub_to_second(0)
    assert playback.snapshot("IMCC")["volume"] == 4
    assert len(playback.bars("IMCC", "1Min", 100, clock.now_et())) == 1
    clock.scrub_to_second(60)
    assert playback.bars("IMCC", "1Min", 100, clock.now_et()) == candles


def test_other_symbol_closed_bars_only_and_date_switch():
    spec = prepare()
    t = datetime.fromtimestamp(spec["start_ts"], clock.ET).isoformat()
    bars_store.write_payload(dict(symbol="SPY", timeframe="1Min", bars=[dict(t=t,o=1,h=9,l=1,c=8,v=20)]))
    clock.scrub_to_second(59)
    assert playback.bars("SPY", "1Min", 100, clock.now_et()) == []
    clock.scrub_to_second(60)
    assert playback.snapshot("SPY")["last"] == 8
    assert playback.snapshot("SPY")["prints"] == []
    playback.select(store.window("SPY", "2026-09-17", "04:00", "20:00"))
    clock.scrub_to_second(60)
    assert playback.snapshot("SPY")["last"] is None
    assert playback.snapshot("IMCC")["prints"] == []


def test_partial_download_does_not_replace_closed_archive_bucket():
    spec = store.window("IMCC", "2026-09-18", "04:00", "09:30")
    job = store.create(spec, "trades")
    a = spec["start_ts"]
    store.commit_page(job["id"], a, [dict(ts=a,price=10,size=2)], a+1, False)
    t = datetime.fromtimestamp(a, clock.ET).isoformat()
    bars_store.write_payload(dict(symbol="IMCC",timeframe="1Min",bars=[dict(t=t,o=10,h=20,l=10,c=20,v=50)]))
    playback.select(spec)
    clock.set_paused(True)
    clock.scrub_to_second(60)
    candles = playback.bars("IMCC", "1Min", 100, clock.now_et())
    assert len(candles) == 1 and candles[0]["v"] == 50
    assert playback.snapshot("IMCC")["volume"] == 50
    assert playback.snapshot("IMCC")["source"] == "mixed"



def test_retained_candles_require_complete_download_and_survive_cache_eviction():
    spec = store.window("F", "2026-09-18", "04:00", "20:00")
    job = store.create(spec, "bars")
    t = datetime.fromtimestamp(spec["start_ts"], clock.ET).isoformat()
    store.save_candles(job["id"], [dict(t=t,o=10,h=20,l=10,c=20,v=50)])
    playback.select(spec)
    clock.set_paused(True)
    clock.scrub_to_second(60)
    assert playback.bars("F", "1Min",100,clock.now_et()) == []
    job["status"] = "complete"
    store.save(job)
    assert playback.bars("F", "1Min",100,clock.now_et())[0]["v"] == 50
    clock.scrub_to_second(59)
    assert playback.bars("F", "1Min",100,clock.now_et()) == []


def test_select_without_download_creates_no_job_and_shows_no_prints():
    spec = store.window("SPY", "2026-09-18", "04:00", "09:30")
    selected = playback.select(spec)
    assert store.jobs() == []
    assert selected["download_status"] == "missing" and selected["trade_count"] == 0
    assert playback.snapshot("SPY")["prints"] == []


def test_reloading_same_window_keeps_playhead_and_new_window_starts_at_open():
    spec = prepare()
    clock.scrub_to_second(80)
    before = clock.now_et()
    playback.select(spec)
    assert clock.is_paused() and clock.now_et() == before
    playback.select(store.window("IMCC", "2026-09-18", "05:00", "09:30"))
    assert clock.is_paused() and (clock.now_et().hour, clock.now_et().minute) == (5, 0)


def test_return_to_sim1_keeps_pause_and_time_of_day_on_sim1_date():
    from sim import replay
    spec = store.window("IMCC", "2026-09-18", "16:00", "20:00")
    playback.select(spec)
    clock.set_paused(True)
    clock.scrub_to_second(3600)  # 17:00 inside the custom window
    replay.set_replay(None, None)
    now = clock.now_et()
    assert playback.status() is None and clock.is_paused()
    assert (now.hour, now.minute) == (17, 0)
    assert now.date() == datetime.now(clock.ET).date()
    assert clock.status_payload()["minute_max"] == 960


def test_unreported_prints_stay_in_tape_but_not_candles_last_or_volume():
    """IMCC acceptance: IBKR bars equal reported prints only (odd-lot TI/FTI excluded)."""
    spec = store.window("IMCC", "2026-09-18", "04:00", "09:30")
    job = store.create(spec, "trades")
    a = spec["start_ts"]
    rows = [dict(ts=a, price=10, size=100), dict(ts=a + 5, price=12, size=7, unreported=True),
            dict(ts=a + 10, price=10.5, size=50)]
    store.commit_page(job["id"], a, rows, spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    clock.scrub_to_second(60)
    candle = playback.bars("IMCC", "1Min", 10, clock.now_et())[0]
    assert (candle["h"], candle["c"], candle["v"]) == (10.5, 10.5, 150)
    snap = playback.snapshot("IMCC")
    assert (snap["last"], snap["volume"], len(snap["prints"])) == (10.5, 150, 3)
    assert snap["prints"][1]["unreported"] is True
