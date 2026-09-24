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


def test_clearing_the_window_keeps_pause_and_time_of_day_on_the_default_date(monkeypatch):
    from sim import replay
    # Saturday wall: with nothing selected the session date is the last open
    # exchange day.
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


def leaderboard_prev_close(symbol, day, close):
    """IBKR's tick 9 as the leaderboard recorded it for that symbol-day (#542)."""
    from leaderboard import store as lb_store
    from leaderboard.rows import make_row
    minute = int(datetime.fromisoformat(f"{day}T09:30:00").replace(tzinfo=clock.ET).timestamp())
    with lb_store.connect() as db:
        lb_store.write_batch(db, rows=[make_row(symbol=symbol, minute_ts=minute, board="gainers",
                                                source="recorded", rank=1, price=5, prev_close=close)])


def test_snapshot_quote_head_open_high_low_and_prior_close():
    """The replay quote head uses reached reported prints and IBKR's prior close."""
    bars_store.write_payload(dict(symbol="IMCC", timeframe="1Day", bars=[
        dict(t="2026-09-17T00:00:00Z", o=1, h=2, l=1, c=9.9, v=10),
        # The replayed session's own daily bar is future information at 04:01.
        dict(t="2026-09-18T00:00:00Z", o=1, h=99, l=1, c=42, v=10),
    ]))
    leaderboard_prev_close("IMCC", "2026-09-18", 9.5)
    prepare()
    clock.scrub_to_second(60)
    snap = playback.snapshot("IMCC")
    assert (snap["open"], snap["high"], snap["low"], snap["last"]) == (10, 20, 10, 20)
    assert snap["prev_close"] == 9.5
    clock.scrub_to_second(0)
    snap = playback.snapshot("IMCC")
    assert (snap["open"], snap["high"], snap["low"]) == (10, 10, 10)


def test_prior_close_is_never_a_1559_close_or_an_extended_daily_bar():
    """#542: the 15:59 bar is the last trade before the closing auction; the stored
    daily bar is fetched with extended hours and ends on the last after-hours trade."""
    bars_store.write_payload(dict(symbol="IMCC", timeframe="1Day", bars=[
        dict(t="2026-09-17T00:00:00Z", o=1, h=2, l=1, c=762.08, v=10)]))
    bars_store.write_payload(dict(symbol="IMCC", timeframe="1Min", bars=[
        dict(t="2026-09-17T19:59:00Z", o=1, h=2, l=1, c=762.63, v=10),
        dict(t="2026-09-17T23:59:00Z", o=1, h=2, l=1, c=762.07, v=10)]))
    prepare()
    assert playback.snapshot("IMCC")["prev_close"] is None
    # The regular-hours close a download stored for this symbol-day answers.
    job = store.find(store.window("IMCC", "2026-09-18", "04:00", "09:30"), "trades")
    store.update(job["id"], prior_close=dict(close=762.52, date="2026-09-17", source="ibkr_rth_daily"))
    playback.select(store.window("IMCC", "2026-09-18", "04:00", "09:30"))
    assert playback.snapshot("IMCC")["prev_close"] == 762.52


def test_prior_close_miss_is_fixed_until_an_explicit_reload():
    prepare()
    assert playback.snapshot("IMCC")["prev_close"] is None
    leaderboard_prev_close("IMCC", "2026-09-18", 2.11)
    assert playback.snapshot("IMCC")["prev_close"] is None
    playback.select(store.window("IMCC", "2026-09-18", "04:00", "09:30"))
    assert playback.snapshot("IMCC")["prev_close"] == 2.11


def test_prior_close_skips_weekends_and_holidays():
    """The download keeps the close dated the exchange session before its day -- never an older one."""
    from sim import prior_close
    # Tuesday 2026-09-08 follows Labor Day: the prior session is Friday 09-04.
    assert prior_close.prior_session_close([("2026-09-04", 3.5), ("2026-09-07", 9.9)], "2026-09-08") == (
        "2026-09-04", 3.5)
    # Weeks-old daily close (PFSA: 25.19 on 08-18 vs ~2.07 on 09-18) never becomes prev_close.
    assert prior_close.prior_session_close([("2026-08-18", 25.19)], "2026-09-18") is None


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


# --- D-056: replay candles must match IBKR's own bar presentation -----------


def prepare_subpenny():
    """Sub-penny prints, two silent minutes, then a later print."""
    spec = store.window("SPY", "2026-09-18", "04:00", "09:30")
    job = store.create(spec, "trades")
    a = spec["start_ts"]
    rows = [dict(ts=a + sec, price=price, size=size) for sec, price, size in
            [(0, 763.3041, 10), (30, 762.8161, 5), (180, 763.50, 4)]]
    store.commit_page(job["id"], a, rows, spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    return spec


def test_print_built_candles_round_to_the_cent_like_ibkr():
    prepare_subpenny()
    clock.scrub_to_second(60)
    first = playback.bars("SPY", "1Min", 100, clock.now_et())[0]
    # open/close half-up, high up, low down -- the rule that reproduced IBKR's
    # own TRADES bars with zero mismatches over the SPY reconciliation.
    assert (first["o"], first["c"]) == (763.30, 762.82)
    assert first["h"] == 763.31 and first["l"] == 762.81
    assert first["v"] == 15


def test_silent_minutes_become_flat_zero_volume_bars():
    prepare_subpenny()
    clock.scrub_to_second(240)
    candles = playback.bars("SPY", "1Min", 100, clock.now_et())
    assert len(candles) == 4, [c["t"] for c in candles]
    flat = candles[1:3]
    for bar in flat:
        assert bar["v"] == 0
        assert bar["o"] == bar["h"] == bar["l"] == bar["c"] == 762.82
        assert not bar["partial"]
    assert candles[3]["v"] == 4 and candles[3]["c"] == 763.50


def test_a_quiet_tail_keeps_the_chart_level_with_the_playhead():
    prepare_subpenny()
    clock.scrub_to_second(300)
    candles = playback.bars("SPY", "1Min", 100, clock.now_et())
    # Without the tail fill the pane stopped at the last print (180) while
    # Time & Sales ran on, so a quiet stretch read as a stalled chart.
    assert len(candles) == 5
    assert candles[-1]["v"] == 0 and candles[-1]["c"] == 763.50


def test_flat_bars_are_never_invented_before_the_first_print():
    prepare_subpenny()
    clock.scrub_to_second(60)
    candles = playback.bars("SPY", "1Min", 100, clock.now_et())
    assert len(candles) == 1  # the session does not start before it started
