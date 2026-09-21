"""Replay prints get a real side from the local L2 recording, or none (AGENTS.md §3).

The operator's rule: real colours, never faked. A historical print is coloured
only when the recorded quote provably held across its whole second, and then by
the live tape's own rule -- so replay shows what the live tape would have shown,
and everything the recording cannot decide stays uncoloured.
"""
import pytest

import l2.batch as l2_batch
import l2.db as l2_db
from l2.store import record_snapshot
from sim import history_playback as playback, history_sides, history_store as store
from sim import session_clock as clock

S = 1_789_740_000  # a whole second inside the window below


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_SIM_HISTORY_DIR", str(tmp_path / "history"))
    monkeypatch.setattr(l2_db, "cache_dir", lambda: tmp_path)
    l2_batch.clear_queues_for_tests()
    clock.reset_for_tests()
    playback.clear()
    history_sides.clear()
    yield
    l2_batch.clear_queues_for_tests()
    clock.reset_for_tests()
    playback.clear()
    history_sides.clear()


def book_at(ts: float, bid: float, ask: float, symbol: str = "IMCC") -> None:
    l2_db.init_db()
    record_snapshot("rec", symbol, "depth", S, ts, {
        "bids": [{"price": bid, "size": 100}], "asks": [{"price": ask, "size": 100}],
        "l1_fallback": False,
    }, session_id="s")


def prt(price: float, ts: int = S, **kw) -> dict:
    return dict(ts=ts, price=price, size=100, **kw)


def test_steady_recorded_quote_colours_with_the_live_rule():
    book_at(S - 0.4, 5.00, 5.02)
    book_at(S + 0.5, 5.00, 5.02)
    book_at(S + 1.3, 5.00, 5.02)
    prints = [prt(5.02), prt(5.00), prt(5.01)]
    assert history_sides.attach_recorded_sides("IMCC", prints) == 3
    assert [p["side"] for p in prints] == ["ask", "bid", "between"]
    assert (prints[0]["bid"], prints[0]["ask"], prints[0]["side_source"]) == (5.00, 5.02, "recorded_book")


def test_a_quote_change_inside_the_second_leaves_the_print_uncoloured():
    book_at(S - 0.4, 5.00, 5.02)
    book_at(S + 0.5, 5.01, 5.03)  # moved during the print's second
    book_at(S + 1.3, 5.01, 5.03)
    prints = [prt(5.02)]
    assert history_sides.attach_recorded_sides("IMCC", prints) == 0
    assert (prints[0]["side"], prints[0]["bid"], prints[0]["ask"]) == (None, None, None)


def test_no_book_on_one_side_of_the_second_is_not_enough():
    book_at(S - 0.4, 5.00, 5.02)  # nothing recorded after the print's second
    prints = [prt(5.02)]
    assert history_sides.attach_recorded_sides("IMCC", prints) == 0
    assert prints[0]["side"] is None


def test_a_stale_book_does_not_decide_the_second():
    book_at(S - 10, 5.00, 5.02)   # far outside the freshness budget
    book_at(S + 1.3, 5.00, 5.02)
    assert history_sides.attach_recorded_sides("IMCC", [prt(5.02)]) == 0


def test_unreported_prints_are_never_coloured():
    book_at(S - 0.4, 5.00, 5.02)
    book_at(S + 1.3, 5.00, 5.02)
    prints = [prt(5.02, unreported=True)]
    assert history_sides.attach_recorded_sides("IMCC", prints) == 0
    assert prints[0]["side"] is None


def test_another_symbols_recording_colours_nothing():
    book_at(S - 0.4, 5.00, 5.02, symbol="SPY")
    book_at(S + 1.3, 5.00, 5.02, symbol="SPY")
    assert history_sides.attach_recorded_sides("IMCC", [prt(5.02)]) == 0


def test_no_l2_db_at_all_means_uncoloured_not_an_error():
    prints = [prt(5.02)]
    assert history_sides.attach_recorded_sides("IMCC", prints) == 0
    assert prints[0]["side"] is None


def test_the_replay_snapshot_carries_recorded_sides_and_their_count():
    spec = store.window("IMCC", "2026-09-18", "04:00", "09:30")
    at = spec["start_ts"] + 60
    job = store.create(spec, "trades")
    store.commit_page(job["id"], spec["start_ts"],
                      [dict(ts=at, price=5.02, size=100), dict(ts=at + 5, price=5.01, size=100)],
                      spec["end_ts"], True)
    playback.select(spec)
    clock.set_paused(True)
    book_at(at - 0.4, 5.00, 5.02)
    book_at(at + 1.3, 5.00, 5.02)
    clock.scrub_to_second(70)
    snap = playback.snapshot("IMCC")
    by_ts = {p["ts"]: p for p in snap["prints"]}
    assert by_ts[at]["side"] == "ask" and by_ts[at]["side_source"] == "recorded_book"
    assert by_ts[at + 5]["side"] is None  # no book around that second
    assert snap["sides_recorded"] == 1
    # The snapshot-level quote stays null: a recorded book is not a quote stream.
    assert snap["bid"] is None and snap["ask"] is None
