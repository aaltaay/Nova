"""Where a practice fill's price comes from: the replay, or the live feed, never a guess."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from constants_practice import PRACTICE_NO_LIVE_PRINT_CODE, PRACTICE_NO_LIVE_PRINT_REASON
from practice.reference import LiveReference, ReplayReference, top_of_book
from sim.fill_model import (
    BASIS_LIVE_PRINT,
    BASIS_LIVE_QUOTE,
    BASIS_PRINT_CROSS,
    BASIS_QUOTE,
    Fill,
    Reference,
    at_placement,
    on_print,
)

NOW = 1_000.0
BOOK = {
    "bids": [{"price": 9.97, "size": 2}, {"price": 9.98, "size": 1}],
    "asks": [{"price": 10.03, "size": 1}, {"price": 10.02, "size": 1}],
    "l1_fallback": False,
}


class Frozen(LiveReference):
    def now_ts(self) -> float:
        return NOW


@pytest.fixture
def live(monkeypatch):
    """Fake the three live sources the Paper reference reads: L1 ticks, the depth book, the tape archive."""
    from ibkr import ticks
    from ibkr.depth import state as depth_state
    from l2 import tape

    fresh: set[str] = set()
    quotes: dict[str, dict] = {}
    books: dict[str, dict] = {}
    watched: set[str] = set()
    trades: list[dict] = []
    monkeypatch.setattr(ticks, "is_fresh", lambda sym, max_age: sym in fresh)
    monkeypatch.setattr(
        ticks, "last_quotes",
        lambda symbols=None: {s: quotes[s] for s in (symbols or list(quotes)) if s in quotes},
    )
    monkeypatch.setattr(depth_state, "current_book", lambda sym: books.get(sym))
    monkeypatch.setattr(tape, "is_watched", lambda sym: sym.upper() in watched)
    monkeypatch.setattr(
        tape, "get_trades_in_range",
        lambda sym, a, b: [r for r in trades if r["symbol"] == sym and a <= r["ts"] <= b],
    )
    return SimpleNamespace(fresh=fresh, quotes=quotes, books=books, watched=watched, trades=trades)


def test_a_fresh_last_with_the_live_book_fills_at_the_live_quote(live) -> None:
    live.fresh.add("IMCC")
    live.quotes["IMCC"] = {"price": 10.0, "last_update_ts": NOW, "last_trade_ts": NOW - 2}
    live.books["IMCC"] = BOOK
    ref = Frozen().reference("imcc")
    assert (ref.last, ref.bid, ref.ask, ref.live) == (10.0, 9.98, 10.02, True)
    assert at_placement("BUY", "MKT", ref) == Fill(10.02, BASIS_LIVE_QUOTE)
    assert at_placement("SELL", "MKT", ref) == Fill(9.98, BASIS_LIVE_QUOTE)
    assert Frozen().admission("IMCC") == (True, "OK", None)


def test_a_fresh_last_without_a_book_fills_at_the_live_print(live) -> None:
    live.fresh.add("IMCC")
    live.quotes["IMCC"] = {"price": 10.0, "last_trade_ts": NOW - 2}
    ref = Frozen().reference("IMCC")
    assert (ref.last, ref.bid, ref.ask) == (10.0, None, None)
    assert at_placement("BUY", "MKT", ref) == Fill(10.0, BASIS_LIVE_PRINT)


def test_a_live_line_whose_last_trade_is_old_is_not_a_live_print(live) -> None:
    """#541: a quote change keeps the line fresh; the 06:40 trade is still not a price now."""
    live.fresh.add("IMCC")
    live.quotes["IMCC"] = {"price": 4.10, "last_update_ts": NOW, "last_trade_ts": NOW - 3 * 3600}
    ref = Frozen().reference("IMCC")
    assert ref.last is None
    assert Frozen().admission("IMCC") == (False, PRACTICE_NO_LIVE_PRINT_REASON, PRACTICE_NO_LIVE_PRINT_CODE)
    # A limit at 4.20 can no longer fill at the old 4.10 with no book open.
    assert at_placement("BUY", "LMT", ref, limit=4.20) is None


def test_the_prior_close_before_the_first_trade_is_never_a_price(live) -> None:
    """#541: a line with no trade today carries IBKR's prior close (``close_fallback``)."""
    live.fresh.add("IMCC")
    live.quotes["IMCC"] = {"price": 9.52, "last_trade_ts": NOW - 1, "quote_quality": "close_fallback"}
    assert Frozen().reference("IMCC").last is None
    assert Frozen().admission("IMCC")[2] == PRACTICE_NO_LIVE_PRINT_CODE


def test_an_unknown_trade_time_leaves_the_decision_to_the_tape(live) -> None:
    live.fresh.add("IMCC")
    live.quotes["IMCC"] = {"price": 10.0}  # no Last Timestamp from IBKR
    live.watched.add("IMCC")
    live.trades.append({"symbol": "IMCC", "ts": NOW - 3, "price": 9.9, "conditions": ""})
    assert Frozen().reference("IMCC").last == 9.9


def test_a_replay_reference_keeps_the_replay_basis() -> None:
    assert at_placement("BUY", "MKT", Reference(10.0, 9.98, 10.02)) == Fill(10.02, BASIS_QUOTE)


def test_a_stale_last_falls_back_to_the_newest_recent_archived_print(live) -> None:
    live.quotes["IMCC"] = {"price": 10.0}  # present but not fresh
    live.watched.add("IMCC")
    live.trades.extend([
        {"symbol": "IMCC", "ts": NOW - 10, "price": 9.5},
        {"symbol": "IMCC", "ts": NOW - 5, "price": 9.7},
        {"symbol": "IMCC", "ts": NOW - 60, "price": 9.0},  # outside the window
    ])
    assert Frozen().reference("IMCC").last == 9.7
    assert Frozen().admission("IMCC")[0] is True


def test_no_fresh_last_and_no_recent_print_refuses_and_never_guesses(live) -> None:
    live.quotes["IMCC"] = {"price": 10.0}
    live.books["IMCC"] = BOOK  # a book alone is not a price a fill may read
    live.watched.add("IMCC")
    live.trades.append({"symbol": "IMCC", "ts": NOW - 100, "price": 9.0})
    ref = Frozen().reference("IMCC")
    assert ref.last is None and ref.bid == 9.98
    assert Frozen().admission("IMCC") == (False, PRACTICE_NO_LIVE_PRINT_REASON, PRACTICE_NO_LIVE_PRINT_CODE)
    assert Frozen().admission("")[2] == PRACTICE_NO_LIVE_PRINT_CODE


def test_an_unwatched_symbol_has_no_archived_print_to_fall_back_to(live) -> None:
    live.trades.append({"symbol": "IMCC", "ts": NOW - 1, "price": 9.9})
    assert Frozen().reference("IMCC").last is None
    assert Frozen().prints_between("IMCC", 0, NOW) == []


def test_prints_between_is_half_open_oldest_first_and_drops_junk(live) -> None:
    live.watched.add("IMCC")
    live.trades.extend([
        {"symbol": "IMCC", "ts": 10.0, "price": 9.0},
        {"symbol": "IMCC", "ts": 20.0, "price": 9.1},
        {"symbol": "IMCC", "ts": 25.0, "price": None},
        {"symbol": "IMCC", "ts": 30.0, "price": 9.2},
    ])
    assert Frozen().prints_between("imcc", 10.0, 30.0) == [(20.0, 9.1), (30.0, 9.2)]
    assert Frozen().prints_between("IMCC", 30.0, 10.0) == []


def test_volume_only_prints_never_set_the_last_or_fill_a_resting_order(live) -> None:
    """#511: on 2026-09-23 PLTR printed FINRA ``190.38 x 100  4 W`` against a 192.64 x 192.80 book."""
    live.watched.add("PLTR")
    live.books["PLTR"] = {"bids": [{"price": 192.64}], "asks": [{"price": 192.80}]}
    live.trades.extend([
        {"symbol": "PLTR", "ts": NOW - 9, "price": 192.70, "conditions": "@ T", "unreported": False},
        # Stored before the archive kept IBKR's flag: judged by its conditions.
        {"symbol": "PLTR", "ts": NOW - 7, "price": 190.38, "conditions": "4 W", "unreported": None},
        {"symbol": "PLTR", "ts": NOW - 6, "price": 190.10, "conditions": "I"},
        # IBKR flagged it unreported without a code the rule lists.
        {"symbol": "PLTR", "ts": NOW - 5, "price": 190.20, "conditions": "", "unreported": True},
    ])
    assert Frozen().reference("PLTR").last == 192.70  # never the average-price print
    prints = Frozen().prints_between("PLTR", NOW - 10, NOW)
    assert prints == [(NOW - 9, 192.70)]
    # A resting buy limit at 191 sees no print at or under it ...
    assert [on_print("BUY", "LMT", px, limit=191.0) for _, px in prints] == [None]
    # ... until a print that sets a price reaches it.
    live.trades.append({"symbol": "PLTR", "ts": NOW - 1, "price": 190.95, "conditions": "@ F", "unreported": False})
    crossed = Frozen().prints_between("PLTR", NOW - 9, NOW)
    assert crossed == [(NOW - 1, 190.95)]
    assert on_print("BUY", "LMT", crossed[0][1], limit=191.0) == Fill(191.0, BASIS_PRINT_CROSS)


def test_only_volume_only_prints_in_the_window_is_no_live_print(live) -> None:
    live.watched.add("PLTR")
    live.trades.append({"symbol": "PLTR", "ts": NOW - 2, "price": 190.38, "conditions": "4 W"})
    assert Frozen().reference("PLTR").last is None
    assert Frozen().admission("PLTR") == (False, PRACTICE_NO_LIVE_PRINT_REASON, PRACTICE_NO_LIVE_PRINT_CODE)


def test_top_of_book_picks_the_best_prices_and_ignores_junk() -> None:
    assert top_of_book(BOOK) == (9.98, 10.02)
    assert top_of_book(None) == (None, None)
    assert top_of_book({"bids": [{"price": 0}], "asks": [{"price": "x"}]}) == (None, None)


def test_replay_reference_delegates_to_sim_practice_at_call_time(monkeypatch) -> None:
    from sim import practice

    monkeypatch.setattr(practice, "reference", lambda sym: Reference(7.0) if sym == "IMCC" else Reference(None))
    monkeypatch.setattr(practice, "admission", lambda sym: (sym == "IMCC", "why", None if sym == "IMCC" else "SIM_X"))
    monkeypatch.setattr(practice, "prints_between", lambda sym, a, b: [(a + 1, 7.5)])
    monkeypatch.setattr(practice, "playhead_ts", lambda: 42.0)
    monkeypatch.setattr(practice, "loaded", lambda: practice.Loaded("historical", "IMCC", ("k", "IMCC")))
    ref = ReplayReference()
    assert ref.reference("IMCC") == Reference(7.0) and ref.reference("IMCC").live is False
    assert ref.admission("SPY") == (False, "why", "SIM_X")
    assert ref.prints_between("IMCC", 1.0, 2.0) == [(2.0, 7.5)]
    assert ref.now_ts() == 42.0 and ref.replay_key() == ("k", "IMCC")
    monkeypatch.setattr(practice, "loaded", lambda: None)
    assert ref.replay_key() is None
