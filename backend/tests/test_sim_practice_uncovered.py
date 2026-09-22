"""An undownloaded stretch of a historical window has no market (QA R34, 2026-09-22).

The snapshot prices an uncovered playhead from a 1-minute candle close so the
chart has a last, but a practice fill there used to be labelled ``last_print``
and a manual order was admitted -- no print was downloaded at that second. Now
the Sim reference carries no price there: an order is refused ``SIM_NO_PRICE``
("Not downloaded ..."), and a protective close gets flat at the last mark with
``fill_basis: "last_mark"``.
"""
from __future__ import annotations

import pytest

from archive import db
from capture import recorder
from constants_sim import SIM_NO_PRICE_REASON, SIM_NOT_DOWNLOADED_REASON
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


def partial_download(covered_sec: int = 100):
    """IMCC 04:00-09:30 with only the first ``covered_sec`` seconds downloaded."""
    spec = store.window("IMCC", DAY, "04:00", "09:30")
    job = store.create(spec, "trades")
    a = spec["start_ts"]
    rows = [dict(ts=a + sec, price=price, size=100) for sec, price in ((10, 10.0), (30, 11.0), (60, 12.0))]
    store.commit_page(job["id"], a, rows, a + covered_sec, False)
    playback.select(spec)
    clock.set_paused(True)
    return spec


def test_a_covered_second_still_trades_at_its_last_print() -> None:
    partial_download()
    clock.scrub_to_second(40)
    assert practice.admission("IMCC") == (True, "OK", None)
    assert practice.reference("IMCC").last == 11.0


def test_an_undownloaded_second_is_refused_not_filled_at_a_candle() -> None:
    partial_download()
    clock.scrub_to_second(150)
    assert playback.snapshot("IMCC")["covered"] is False
    assert practice.reference("IMCC").last is None
    assert practice.admission("IMCC") == (False, SIM_NOT_DOWNLOADED_REASON, "SIM_NO_PRICE")
    raw = broker.place("IMCC", "BUY", 1, "MKT")
    assert raw["ok"] is False and raw["reason_code"] == "SIM_NO_PRICE"
    assert broker.positions() == []


def test_a_protective_close_there_fills_at_the_last_mark_and_says_so() -> None:
    partial_download()
    clock.scrub_to_second(40)
    assert broker.place("IMCC", "BUY", 2, "MKT")["ok"]
    clock.scrub_to_second(150)
    raw = broker.place("IMCC", "SELL", 2, "MKT", protective=True, source="flatten")
    assert raw["ok"] and raw["broker_status"] == "Filled"
    row = broker.closed_orders()[0]
    assert row["fill_basis"] == "last_mark"
    assert row["avg_fill_price"] == 11.0
    assert broker.positions() == []


def test_before_the_window_has_printed_the_reason_stays_no_trade_yet() -> None:
    partial_download()
    clock.scrub_to_second(5)
    assert practice.admission("IMCC") == (False, SIM_NO_PRICE_REASON, "SIM_NO_PRICE")
