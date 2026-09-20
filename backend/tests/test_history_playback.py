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
    assert playback.bars("SPY", "1Min", 100, clock.now_et())[-1]["c"] == 8
    assert playback.snapshot("SPY")["active"] is False
    assert playback.snapshot("SPY")["last"] is None
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
    assert playback.bars("F", "1Min",100,clock.now_et()) == []
    playback.select(spec)  # Explicit reload publishes newly completed data.
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


def test_return_to_sim1_keeps_pause_and_time_of_day_on_sim1_date(monkeypatch):
    from sim import replay
    # Saturday wall: the SIM1 session date is the last open exchange day.
    monkeypatch.setattr(clock, "_wall_et_now", lambda: datetime(2026, 9, 19, 10, 0, tzinfo=clock.ET))
    spec = store.window("IMCC", "2026-09-18", "16:00", "20:00")
    playback.select(spec)
    clock.set_paused(True)
    clock.scrub_to_second(3600)  # 17:00 inside the custom window
    replay.set_replay(None, None)
    now = clock.now_et()
    assert playback.status() is None and clock.is_paused()
    assert (now.hour, now.minute) == (17, 0)
    assert now.date().isoformat() == "2026-09-18"
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


def test_snapshot_quote_head_open_high_low_and_prior_close():
    """The replay quote head uses reached reported prints and the prior session close."""
    bars_store.write_payload(dict(symbol="IMCC", timeframe="1Day", bars=[
        dict(t="2026-09-17T00:00:00Z", o=1, h=2, l=1, c=9.5, v=10),
        # The replayed session's own daily bar is future information at 04:01.
        dict(t="2026-09-18T00:00:00Z", o=1, h=99, l=1, c=42, v=10),
    ]))
    prepare()
    clock.scrub_to_second(60)
    snap = playback.snapshot("IMCC")
    assert (snap["open"], snap["high"], snap["low"], snap["last"]) == (10, 20, 10, 20)
    assert snap["prev_close"] == 9.5
    clock.scrub_to_second(0)
    snap = playback.snapshot("IMCC")
    assert (snap["open"], snap["high"], snap["low"]) == (10, 10, 10)


def test_prior_close_prefers_regular_session_close_over_extended_daily_bar():
    # SPY 2026-09-17: 15:59 ET bar closed 762.63; the useRTH=False daily bar ends at 20:00 (762.08).
    bars_store.write_payload(dict(symbol="IMCC", timeframe="1Day", bars=[
        dict(t="2026-09-17T00:00:00Z", o=1, h=2, l=1, c=762.08, v=10)]))
    bars_store.write_payload(dict(symbol="IMCC", timeframe="1Min", bars=[
        dict(t="2026-09-17T19:59:00Z", o=1, h=2, l=1, c=762.63, v=10),
        dict(t="2026-09-17T23:59:00Z", o=1, h=2, l=1, c=762.07, v=10)]))
    prepare()
    assert playback.snapshot("IMCC")["prev_close"] == 762.63


def test_prior_close_is_never_an_older_session_and_reload_invalidates_a_miss():
    # Weeks-old daily close (PFSA: 25.19 on 08-18 vs ~2.07 on 09-18) must not become prev_close.
    bars_store.write_payload(dict(symbol="IMCC", timeframe="1Day", bars=[
        dict(t="2026-08-18T00:00:00Z", o=1, h=2, l=1, c=25.19, v=10)]))
    prepare()
    assert playback.snapshot("IMCC")["prev_close"] is None
    bars_store.write_payload(dict(symbol="IMCC", timeframe="1Day", bars=[
        dict(t="2026-09-17T00:00:00Z", o=1, h=2, l=1, c=2.11, v=10)]))
    assert playback.snapshot("IMCC")["prev_close"] is None
    playback.select(store.window("IMCC", "2026-09-18", "04:00", "09:30"))
    assert playback.snapshot("IMCC")["prev_close"] == 2.11


def test_prior_close_skips_weekends_and_holidays():
    spec = store.window("IMCC", "2026-09-08", "04:00", "09:30")  # Tuesday after Labor Day
    bars_store.write_payload(dict(symbol="IMCC", timeframe="1Day", bars=[
        dict(t="2026-09-04T00:00:00Z", o=1, h=2, l=1, c=3.5, v=10)]))
    playback.select(spec)
    assert playback.snapshot("IMCC")["prev_close"] == 3.5


def test_hot_snapshots_and_warm_timeframe_bars_do_not_read_disk(monkeypatch):
    prepare()
    clock.scrub_to_second(60)
    playback.bars('IMCC', '5Min', 100, clock.now_et())
    def unexpected(*args, **kwargs):
        raise AssertionError('hot path touched disk')
    monkeypatch.setattr(store, 'connect', unexpected)
    monkeypatch.setattr(bars_store, 'read', unexpected)
    for second in (60, 0, 80, 60):
        clock.scrub_to_second(second)
        snap = playback.snapshot('IMCC')
        assert all(row['ts'] <= clock.now_et().timestamp() for row in snap['prints'])
        for timeframe in ('1Min', '5Min'):
            playback.bars('IMCC', timeframe, 100, clock.now_et())
    assert [row['ordinal'] for row in playback.snapshot('IMCC')['prints']] == [3, 2, 1, 0]


def test_load_does_not_block_snapshots_and_clear_fences_inflight_load(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    spec = prepare()
    entered, release = threading.Event(), threading.Event()
    real_read = store.read_prints
    def slow_read(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return real_read(*args, **kwargs)
    monkeypatch.setattr(store, 'read_prints', slow_read)
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = executor.submit(playback.select, spec)
        try:
            assert entered.wait(2)
            current = executor.submit(playback.snapshot, 'IMCC').result(timeout=1)
            assert current['active'] and current['selection']['symbol'] == 'IMCC'
            playback.clear()
        finally:
            release.set()
        with pytest.raises(ValueError, match='selection changed'):
            pending.result(timeout=3)
    assert playback.status() is None


def test_print_limit_refuses_without_losing_previous_selection(monkeypatch):
    spec = prepare()
    before = playback.status()
    monkeypatch.setattr(playback, 'SIM_HISTORY_MAX_SELECTION_PRINTS', 2)
    with pytest.raises(ValueError, match='narrow the window'):
        playback.select(spec)
    assert playback.status() == before
    assert len(playback.snapshot('IMCC')['prints']) == 2


def test_cached_results_and_selection_cannot_be_mutated_by_callers():
    prepare()
    clock.scrub_to_second(60)
    first = playback.bars('IMCC', '1Min', 100, clock.now_et())
    first[-1]['c'] = 999
    snap = playback.snapshot('IMCC')
    snap['selection']['symbol'] = 'WRONG'
    snap['prints'][0]['price'] = 999
    assert playback.snapshot('IMCC')['last'] == 20
    assert playback.status()['symbol'] == 'IMCC'
    assert playback.bars('IMCC', '1Min', 100, clock.now_et())[-1]['c'] == 20
