"""Practice orders trade the loaded real replay (#310). No synthetic instrument."""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from archive import db
from capture import recorder
from sim import broker, capture_player, feed, practice, replay
from sim import history_playback as playback, history_store as store, session_clock as clock

DAY = "2026-09-18"


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


def historical(prints, day: str = DAY):
    spec = store.window("IMCC", day, "04:00", "09:30")
    job = store.create(spec, "trades")
    a = spec["start_ts"]
    rows = [dict(ts=a + sec, price=price, size=100, **extra) for sec, price, extra in prints]
    store.commit_page(job["id"], a, rows, spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    return spec


TAPE = [(10, 10.0, {}), (30, 11.0, {}), (45, 10.4, {}), (60, 12.0, {}),
        (70, 9.9, {"unreported": True})]


def test_nothing_loaded_refuses_every_practice_order() -> None:
    assert practice.loaded() is None
    assert practice.admission("IMCC")[2] == "SIM_NO_REPLAY"
    raw = broker.place("IMCC", "BUY", 1, "MKT")
    assert raw["ok"] is False and raw["reason_code"] == "SIM_NO_REPLAY"
    assert broker.positions() == []


def test_only_the_loaded_symbol_trades() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    assert practice.admission("SPY")[2] == "SIM_SYMBOL_MISMATCH"
    assert practice.admission("IMCC") == (True, "OK", None)


def test_no_practice_order_before_the_replay_first_prints() -> None:
    historical(TAPE)
    clock.scrub_to_second(5)
    assert practice.admission("IMCC")[2] == "SIM_NO_PRICE"


def test_candles_only_window_is_refused_with_a_download_hint() -> None:
    spec = store.window("IMCC", DAY, "04:00", "09:30")
    playback.select(spec)
    clock.set_paused(True)
    assert practice.admission("IMCC")[2] == "SIM_NO_TRADES"


def test_market_order_fills_at_the_last_print_and_is_marked_estimated() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    raw = broker.place("IMCC", "BUY", 10, "MKT")
    assert raw["ok"] and raw["broker_status"] == "Filled"
    row = broker.closed_orders()[0]
    assert row["avg_fill_price"] == 11.0
    assert row["fill_estimated"] is True and row["fill_basis"] == "last_print"


def test_resting_limit_fills_on_a_later_replay_print() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 5, "LMT", limit_price=10.5)
    assert len(broker.open_orders()) == 1
    feed.match_practice_fills()
    clock.scrub_to_second(60)
    filled = feed.match_practice_fills()
    assert [(r["avg_fill_price"], r["fill_basis"]) for r in filled] == [(10.5, "print_cross")]
    assert broker.positions()[0]["market_price"] == 12.0


def test_unreported_prints_never_fill_a_practice_order() -> None:
    historical(TAPE)
    clock.scrub_to_second(60)
    broker.place("IMCC", "BUY", 5, "LMT", limit_price=10.0)
    feed.match_practice_fills()
    clock.scrub_to_second(80)
    assert feed.match_practice_fills() == []
    assert len(broker.open_orders()) == 1


def test_scrubbing_back_before_the_order_forgets_it_for_good() -> None:
    """ADR 020 decision 3: an order placed after the new playhead never happened,
    so no earlier print can fill it and moving forward again never re-places it."""
    historical(TAPE)
    clock.scrub_to_second(60)
    broker.place("IMCC", "BUY", 5, "LMT", limit_price=10.5)
    feed.match_practice_fills()
    clock.scrub_to_second(30)
    assert broker.open_orders() == []
    assert feed.match_practice_fills() == []
    clock.scrub_to_second(50)
    assert feed.match_practice_fills() == []
    assert broker.open_orders() == [] and broker.closed_orders() == []


def test_stop_protects_a_position_on_the_replay() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 5, "MKT")
    broker.place("IMCC", "SELL", 5, "STP", stop_price=10.5)
    feed.match_practice_fills()
    clock.scrub_to_second(60)
    filled = feed.match_practice_fills()
    assert [(r["avg_fill_price"], r["fill_basis"]) for r in filled] == [(10.4, "stop_trigger")]
    assert broker.positions() == []


def test_unloading_the_replay_leaves_nothing_to_flatten() -> None:
    """ADR 020 decision 3: unloading clears the scratch account, so the desk is flat
    already -- a protective close has nothing to close (the last-mark close is the
    Paper venue's path when its live feed goes dark, test_practice_broker)."""
    historical(TAPE)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 5, "MKT")
    playback.clear()
    assert broker.positions() == []
    assert broker.place("IMCC", "SELL", 5, "MKT")["reason_code"] == "SIM_NO_REPLAY"
    assert broker.place("IMCC", "SELL", 5, "MKT", protective=True)["ok"] is False
    assert broker.closed_orders() == []


def test_recorded_capture_fills_market_orders_at_its_quote(isolated) -> None:
    ts = datetime.fromisoformat(DAY + "T10:00:00-04:00").timestamp()
    directory = isolated / "capture" / DAY / "AAPL"
    directory.mkdir(parents=True)
    (directory / "prints.jsonl").write_text(json.dumps(dict(ts=ts, symbol="AAPL", price=10.0)) + "\n")
    (directory / "quotes.jsonl").write_text(
        json.dumps(dict(ts=ts, symbol="AAPL", bid=9.9, ask=10.1, last=10.0)) + "\n")
    assert replay.set_replay(DAY, "AAPL")["replay_ok"]
    clock.set_paused(True)
    clock.scrub_to_second(int(ts - clock.session_bounds_on(clock.now_et())[0].timestamp()))
    assert practice.loaded().source == practice.CAPTURE
    broker.place("AAPL", "BUY", 1, "MKT")
    row = broker.closed_orders()[0]
    assert (row["avg_fill_price"], row["fill_basis"]) == (10.1, "quote")
