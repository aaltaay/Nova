"""Sim replay truth (QA 2026-09-22, fix/qa-sim-replay).

R9 a paused forward scrub still fills; R11 a gap in a recording is a stated
absence; R12 recorded quote rows load; R19 a later downloaded range prices from
prints; R23 a worker that dies early leaves no phantom; R24 odd lots (and #511 every
volume-only print) never fill;
R27 Sim rows carry replay time; C38 a dead download is not "running"; C40 a
finished candle download covers its window; C42 the replay reply carries the
clock; C59 a loading capture is not a failure; R10 the clock carries the
capture's quote.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from archive import db
from capture import recorder
from constants_sim import SIM_NOT_RECORDED_REASON
from sim import broker, capture_player, feed, history_coverage, practice, replay
from sim import history_download, history_playback as playback, history_store as store, session_clock as clock

DAY = "2026-09-18"


def _ts(hms: str) -> float:
    return datetime.fromisoformat(f"{DAY}T{hms}-04:00").timestamp()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setenv("NOVA_SIM_CAPTURE_DIR", str(tmp_path / "capture"))
    monkeypatch.setattr(db, "cache_dir", lambda: tmp_path)
    db.init_db()
    _reset()
    yield tmp_path
    _reset()


def _reset() -> None:
    clock.reset_for_tests()
    playback.clear()
    replay.clear_capture()
    capture_player.reset_for_tests()
    recorder.reset_for_tests()
    broker.reset_for_tests()
    feed.reset_for_tests()


def _second(ts: float) -> int:
    return int(ts - clock.session_bounds_on(clock.now_et())[0].timestamp())


def _capture(root, prints, quotes=(), l2=(), segments=None, symbol="GRML"):
    directory = root / "capture" / DAY / symbol
    directory.mkdir(parents=True)
    (directory / "prints.jsonl").write_text("".join(json.dumps({"symbol": symbol, **p}) + "\n" for p in prints))
    if quotes:
        (directory / "quotes.jsonl").write_text("".join(json.dumps({"symbol": symbol, **q}) + "\n" for q in quotes))
    if l2:
        (directory / "l2.jsonl").write_text("".join(json.dumps({"symbol": symbol, **b}) + "\n" for b in l2))
    if segments is not None:
        (directory / "manifest.json").write_text(json.dumps({"source": "ibkr", "segments": segments}))
    assert replay.set_replay(DAY, symbol)["replay_ok"] is True
    clock.set_paused(True)


# Recorded 10:00-10:10 and 11:30-11:40; nothing between (a restart).
SEGMENTS = [
    {"started_et": f"{DAY}T10:00:00-04:00", "stopped_et": f"{DAY}T10:10:00-04:00", "reason": "restart"},
    {"started_et": f"{DAY}T11:30:00-04:00", "stopped_et": f"{DAY}T11:40:00-04:00", "reason": "operator"},
]


def test_a_gap_in_the_recording_is_a_stated_absence_never_the_market_before_it(isolated) -> None:
    _capture(isolated,
             prints=[{"ts": _ts("10:05:00"), "price": 8.80}, {"ts": _ts("11:35:00"), "price": 9.40}],
             quotes=[{"ts": _ts("10:05:00"), "bid": 8.77, "ask": 8.81, "last": None}],
             l2=[{"ts": _ts("10:05:00"), "bids": [{"price": 8.77, "size": 100}], "asks": [{"price": 8.81, "size": 100}]}],
             segments=SEGMENTS)
    clock.scrub_to_second(_second(_ts("11:00:00")))  # inside the gap
    assert capture_player.covered() is False
    assert capture_player.quote_at() is None and capture_player.recent_prints() == []
    assert capture_player.last_print_at(_ts("11:00:00")) is None
    book = capture_player.book_at()
    assert book["bids"] == [] and book["asks"] == [] and book["recorded"] is False
    assert practice.admission("GRML") == (False, SIM_NOT_RECORDED_REASON, "SIM_NO_PRICE")
    assert broker.place("GRML", "BUY", 1, "MKT")["ok"] is False
    # Inside the second stretch but before its first print: never the 10:05 tape.
    clock.scrub_to_second(_second(_ts("11:31:00")))
    assert capture_player.recent_prints() == [] and capture_player.last_print_at(_ts("11:31:00")) is None
    clock.scrub_to_second(_second(_ts("11:36:00")))
    assert capture_player.last_print_at(_ts("11:36:00")) == 9.40
    quote = capture_player.replay_quote()
    assert quote["covered"] is True and quote["last"] == 9.40


def test_recorded_quote_rows_load_and_the_last_comes_from_the_tape(isolated) -> None:
    _capture(isolated,
             prints=[{"ts": _ts("10:00:00"), "price": 10.0}],
             quotes=[{"ts": _ts("10:00:01"), "bid": 9.95, "bid_size": 100, "ask": 10.05, "ask_size": 200,
                      "last": None, "volume": None}])
    load = replay.status_payload()["replay_load"]
    assert load["counts"]["quotes"] == 1 and load["invalid_rows"] == 0
    clock.scrub_to_second(_second(_ts("10:00:02")))
    quote = capture_player.quote_at()
    assert (quote["bid"], quote["ask"], quote["last"]) == (9.95, 10.05, 10.0)


def test_volume_only_prints_never_set_the_last_or_fill_a_practice_order(isolated) -> None:
    """R24 odd lots, and #511 every print that does not set a price (average price, flagged unreported)."""
    _capture(isolated, prints=[{"ts": _ts("10:00:00"), "price": 10.0},
                               {"ts": _ts("10:00:30"), "price": 9.0, "conditions": "TI"},
                               {"ts": _ts("10:00:33"), "price": 8.8, "conditions": "4 W"},
                               {"ts": _ts("10:00:36"), "price": 8.9, "conditions": "", "unreported": True},
                               {"ts": _ts("10:00:38"), "price": 8.7, "conditions": "", "sets_price": False},
                               {"ts": _ts("10:01:00"), "price": 10.2}])
    clock.scrub_to_second(_second(_ts("10:00:40")))
    assert capture_player.last_print_at(_ts("10:00:40")) == 10.0
    assert practice.prints_between("GRML", _ts("10:00:10"), _ts("10:01:00")) == [(_ts("10:01:00"), 10.2)]


def test_a_resting_limit_never_fills_on_an_average_price_print(isolated) -> None:
    """#511: the PLTR ``4 W`` shape -- a print far under the market is volume, not a price."""
    _capture(isolated, prints=[{"ts": _ts("10:00:00"), "price": 10.0},
                               {"ts": _ts("10:00:30"), "price": 9.0, "conditions": "4 W"}])
    clock.scrub_to_second(_second(_ts("10:00:10")))
    broker.place("GRML", "BUY", 1, "LMT", limit_price=9.5)
    feed.tick()  # anchors the fill cursor at the placement
    clock.scrub_to_second(_second(_ts("10:00:50")))
    feed.tick()
    assert broker.closed_orders() == []


def test_a_paused_forward_scrub_fills_what_it_crossed(isolated) -> None:
    _capture(isolated, prints=[{"ts": _ts("10:00:00"), "price": 10.0}, {"ts": _ts("10:02:00"), "price": 9.5}])
    clock.scrub_to_second(_second(_ts("10:01:00")))
    broker.place("GRML", "BUY", 1, "LMT", limit_price=9.6)
    feed.tick()  # anchors the fill cursor at the placement
    clock.scrub_to_second(_second(_ts("10:05:00")))
    assert clock.is_paused()
    feed.tick()
    closed = broker.closed_orders()
    assert [(row["status"], row["fill_basis"]) for row in closed] == [("Filled", "print_cross")]


def test_sim_rows_carry_the_replay_time_not_the_wall_clock(isolated) -> None:
    _capture(isolated, prints=[{"ts": _ts("10:00:00"), "price": 10.0}])
    clock.scrub_to_second(_second(_ts("10:00:05")))
    broker.place("GRML", "BUY", 1, "MKT")
    row = broker.closed_orders()[0]
    assert row["submitted_at"].startswith(f"{DAY}T14:00:05")
    assert row["filled_at"].startswith(f"{DAY}T14:00:05")


def test_a_capture_still_loading_is_neither_loaded_nor_failed(monkeypatch) -> None:
    monkeypatch.setattr(replay, "_load_info", dict(replay._LOADING))
    status = replay.status_payload()
    assert status["replay_loading"] is True and status["replay_ok"] is None and status["replay_error"] is None
    assert feed.tick() == {}


def test_the_replay_reply_and_the_clock_carry_the_clock_and_the_quote(isolated) -> None:
    from sim.routes import router

    directory = isolated / "capture" / DAY / "GRML"
    directory.mkdir(parents=True)
    (directory / "prints.jsonl").write_text(json.dumps({"symbol": "GRML", "ts": _ts("10:00:00"), "price": 10.0}) + "\n")
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        reply = client.post("/api/sim/replay", json={"date": DAY, "symbol": "GRML"}).json()
        assert reply["replay_ok"] is True and reply["replay_source"] == "capture"
        assert reply["sim_time_et"].startswith(f"{DAY}T10:00") and reply["minute_from_open"] == 360
        assert reply["replay_quote"]["last"] == 10.0 and reply["replay_quote"]["covered"] is True
        assert client.get("/api/sim/clock").json()["replay_quote"]["symbol"] == "GRML"


def _historical(prints, ranges=None):
    spec = store.window("IMCC", DAY, "09:00", "10:00")
    job = store.create(spec, "trades")
    a = spec["start_ts"]
    rows = [dict(ts=a + sec, price=price, size=100) for sec, price in prints]
    store.commit_page(job["id"], a, rows, spec["end_ts"], True)
    if ranges is not None:
        store.update(job["id"], ranges=[[a + x, a + y] for x, y in ranges], status="running")
    return spec, store.get(job["id"])


def test_a_later_downloaded_range_prices_the_last_from_its_print_not_a_candle() -> None:
    spec, _job = _historical([(10, 9.2201), (1500, 9.2709)], ranges=[(0, 600), (1200, 1800)])
    playback.select(spec)
    clock.set_paused(True)
    clock.scrub_to_second(1510)
    snap = playback.snapshot("IMCC")
    assert snap["covered"] is True and snap["last"] == 9.2709


def test_a_dead_worker_is_not_fetching_this_moment_now(monkeypatch) -> None:
    spec, job = _historical([(10, 9.0)], ranges=[(0, 600)])
    playback.select(spec)
    clock.set_paused(True)
    clock.scrub_to_second(900)
    monkeypatch.setattr(store, "stale_after", lambda: 0.0)  # its checkpoint is older than the window
    assert playback.snapshot("IMCC")["selection"]["download_status"] == "interrupted"


def test_a_finished_candle_download_covers_its_window() -> None:
    spec = store.window("IMCC", DAY, "09:00", "10:00")
    job = store.update(store.create(spec, "bars")["id"], status="complete", ranges=[])
    assert history_coverage.job_ranges(job) == [[spec["start_ts"], spec["end_ts"]]]
    from sim.history_progress import progress
    assert progress(job)["progress_pct"] == 100 and progress(job)["downloaded_through"] == spec["end_ts"]


def test_a_worker_that_dies_before_its_first_request_leaves_no_phantom(monkeypatch) -> None:
    import builtins

    spec = store.window("IMCC", DAY, "09:00", "10:00")
    real_import = builtins.__import__

    def broken(name, *args, **kwargs):
        if name == "ibkr.replay_history_gateway":
            raise ImportError("replay gateway unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken)
    job = history_download.begin(spec, "trades")
    for _ in range(200):
        if not history_download._active:
            break
        import time
        time.sleep(0.01)
    assert history_download._active == {}, "a dead worker must release the download slot"
    assert store.get(job["id"])["status"] == "failed"
