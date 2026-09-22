"""The Sim scratch account unwinds with the playhead (ADR 020 decision 3).

Scrubbing backwards: every practice order and fill after the new playhead never
happened -- position, cash, closed orders, the day figures. Scrubbing forward
changes nothing (nothing is re-placed), and the feed matches the tape again
from the new playhead so a resting order can fill on the re-played stretch.
Unloading the replay, or loading another day, starts the account over and the
snapshot's ``replay_key`` names the loaded replay (``None`` once unloaded).
Re-selecting the same window (the download folding new ranges in) keeps it.
"""
from __future__ import annotations

import json
from datetime import datetime

from sim import broker, feed, replay
from sim import history_playback as playback, session_clock as clock
from tests.test_sim_practice import DAY, TAPE, historical, isolated  # noqa: F401 -- autouse fixture

OTHER_DAY = "2026-09-17"
START_CASH = 100_000.0
KEY = ["historical", "IMCC", DAY, "04:00", "09:30"]


def _account() -> dict:
    return broker.snapshot()


def _fresh(snap: dict) -> bool:
    figures = (snap["cash"], snap["positions"], snap["working"], snap["realized_pnl"], snap["fills_today"])
    return figures == (START_CASH, [], [], 0, 0)


def _nothing_on_the_books() -> bool:
    return broker.positions() == [] and broker.open_orders() == [] and broker.closed_orders() == []


# ── scrubbing backwards ───────────────────────────────────────────────────────

def test_scrubbing_back_before_a_fill_forgets_the_order_and_restores_the_cash() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    assert broker.place("IMCC", "BUY", 10, "MKT")["broker_status"] == "Filled"
    before = _account()
    assert before["cash"] < START_CASH and before["positions"][0]["qty"] == 10 and before["fills_today"] == 1
    assert [r["status"] for r in broker.closed_orders()] == ["Filled"]

    clock.scrub_to_second(20)

    assert _nothing_on_the_books()
    after = _account()
    assert _fresh(after) and after["commissions_today"] == 0 and after["replay_key"] == KEY


def test_scrubbing_forward_again_re_places_nothing() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 10, "MKT")
    feed.match_practice_fills()
    clock.scrub_to_second(20)

    clock.scrub_to_second(60)

    assert feed.match_practice_fills() == []
    assert _nothing_on_the_books() and _fresh(_account())


def test_scrubbing_back_between_placement_and_fill_restores_the_resting_order() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    raw = broker.place("IMCC", "BUY", 5, "LMT", limit_price=10.5)
    feed.match_practice_fills()
    clock.scrub_to_second(60)
    assert [r["avg_fill_price"] for r in feed.match_practice_fills()] == [10.5]  # the 10.4 print at 45s
    assert broker.open_orders() == [] and broker.positions()[0]["qty"] == 5

    clock.scrub_to_second(40)  # after the placement, before the fill

    assert broker.positions() == [] and broker.closed_orders() == []
    assert [(r["order_id"], r["status"]) for r in broker.open_orders()] == [(raw["order_id"], "Submitted")]
    assert _account()["cash"] == START_CASH


def test_the_tape_is_matched_again_from_the_new_playhead_after_an_unwind() -> None:
    """The feed cursor moves back with the account: the re-played stretch is not skipped."""
    historical(TAPE)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 5, "LMT", limit_price=10.5)
    feed.match_practice_fills()
    clock.scrub_to_second(60)
    assert len(feed.match_practice_fills()) == 1
    clock.scrub_to_second(40)

    clock.scrub_to_second(60)

    filled = feed.match_practice_fills()
    assert [(r["avg_fill_price"], r["fill_basis"]) for r in filled] == [(10.5, "print_cross")]
    assert broker.positions()[0]["qty"] == 5 and broker.open_orders() == []


def test_a_forward_move_changes_nothing() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 10, "MKT")
    broker.place("IMCC", "SELL", 10, "LMT", limit_price=50.0)

    clock.scrub_to_second(80)

    assert broker.positions()[0]["qty"] == 10
    assert len(broker.open_orders()) == 1 and len(broker.closed_orders()) == 1


def test_following_the_wall_clock_back_from_a_scrub_unwinds_too(monkeypatch) -> None:
    """``clear_scrub`` is a playhead move like any other."""
    historical(TAPE)
    start, _ = clock.session_bounds_on(clock.now_et())
    monkeypatch.setattr(clock, "_wall_et_now", lambda: start.replace(hour=4, minute=0, second=20))
    clock.set_paused(False)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 10, "MKT")
    assert broker.positions()[0]["qty"] == 10

    clock.clear_scrub()  # the wall clock reads 04:00:20 on the replay day: before the fill

    assert clock.status_payload()["second_from_open"] == 20
    assert _nothing_on_the_books()


# ── unloading and loading ─────────────────────────────────────────────────────

def test_unloading_the_replay_clears_the_account_and_its_replay_key() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 10, "MKT")
    broker.place("IMCC", "SELL", 10, "LMT", limit_price=50.0)
    assert _account()["replay_key"] == KEY

    playback.clear()

    snap = _account()
    assert snap["replay_key"] is None and _fresh(snap)
    assert _nothing_on_the_books()


def test_loading_another_day_starts_the_account_over_on_that_day() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 10, "MKT")

    historical(TAPE, day=OTHER_DAY)

    snap = _account()
    assert snap["replay_key"] == ["historical", "IMCC", OTHER_DAY, "04:00", "09:30"]
    assert _fresh(snap) and snap["day_started_et"].startswith(OTHER_DAY)
    assert _nothing_on_the_books()


def test_reselecting_the_same_window_keeps_the_account() -> None:
    spec = historical(TAPE)
    clock.scrub_to_second(30)
    broker.place("IMCC", "BUY", 10, "MKT")

    playback.select(spec)  # the download folded a new range in: same window, same account

    assert broker.positions()[0]["qty"] == 10 and len(broker.closed_orders()) == 1
    assert _account()["replay_key"] == KEY


def test_a_reset_account_keeps_the_operators_starting_cash() -> None:
    historical(TAPE)
    clock.scrub_to_second(30)
    from practice.broker import for_venue

    for_venue("sim").reset(25_000)
    broker.place("IMCC", "BUY", 10, "MKT")

    playback.clear()

    snap = _account()
    assert (snap["starting_cash"], snap["cash"], snap["positions"]) == (25_000, 25_000, [])


# ── recorded captures ─────────────────────────────────────────────────────────

def _capture(root, symbol: str = "AAPL") -> int:
    """Record one print + quote at 10:00 ET and load it; returns its second from open."""
    ts = datetime.fromisoformat(DAY + "T10:00:00-04:00").timestamp()
    directory = root / "capture" / DAY / symbol
    directory.mkdir(parents=True)
    (directory / "prints.jsonl").write_text(json.dumps(dict(ts=ts, symbol=symbol, price=10.0)) + "\n")
    (directory / "quotes.jsonl").write_text(
        json.dumps(dict(ts=ts, symbol=symbol, bid=9.9, ask=10.1, last=10.0)) + "\n")
    assert replay.set_replay(DAY, symbol)["replay_ok"]
    clock.set_paused(True)
    return int(ts - clock.session_bounds_on(clock.now_et())[0].timestamp())


def test_a_recorded_capture_unwinds_with_the_playhead_too(isolated) -> None:
    at = _capture(isolated)
    clock.scrub_to_second(at + 5)
    assert broker.place("AAPL", "BUY", 1, "MKT")["broker_status"] == "Filled"
    assert _account()["replay_key"] == ["capture", "AAPL", DAY]

    clock.scrub_to_second(at - 5)

    assert _nothing_on_the_books() and _fresh(_account())


def test_unloading_a_recorded_capture_clears_the_account(isolated) -> None:
    at = _capture(isolated)
    clock.scrub_to_second(at + 5)
    broker.place("AAPL", "BUY", 1, "MKT")

    assert replay.set_replay(None, None)["replay_source"] == "none"

    snap = _account()
    assert snap["replay_key"] is None and _fresh(snap) and _nothing_on_the_books()
