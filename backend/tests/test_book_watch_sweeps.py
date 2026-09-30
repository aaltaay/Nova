"""A level a print traded through reads traded when IBKR's book shows it gone late (#636, ADR 033)."""
from __future__ import annotations

import json

import pytest

from book_watch import sweep_study, window_study
from book_watch.book import side_view
from book_watch.constants_book_watch import BOOK_WATCH_SWEEP_HOLD_SEC
from book_watch.detector import SymbolWatch
from book_watch.matching import MatchParams, swept_levels

BIDS = [{"price": 9.99, "size": 300, "mm": "NSDQ"}]
ASKS = [{"price": 10.00, "size": 500, "mm": "NSDQ"}, {"price": 10.01, "size": 300, "mm": "ARCA"},
        {"price": 10.02, "size": 300, "mm": "NSDQ"}]
ASKS_AFTER = [{"price": 10.01, "size": 200, "mm": "ARCA"}, {"price": 10.02, "size": 300, "mm": "NSDQ"}]


def _late_book(*, through: dict | None = None, at_best: bool = True, shown_at: float = 2.8,
               asks: list | None = None, mid: list | None = None, after: list | None = None,
               match: MatchParams | None = None) -> dict:
    """A buyer takes the 10.00 offer and prints through it at 1.1; the book shows it gone at ``shown_at``
    and until then shows ``mid`` (by default the offer as it was: the depth line has not caught up)."""
    judged: list = []
    w = SymbolWatch("TEST", num_rows=10, judged=judged, **({"match": match} if match else {}))
    w.on_book(1.0, BIDS, asks or ASKS)
    if at_best:
        w.on_print(1.1, 10.00, 500, lit=True, conditions="")
    if through is not None:
        w.on_print(1.1, through.get("price", 10.01), through.get("size", 100), lit=through.get("lit", True),
                   conditions=through.get("conditions", ""))
    t = 1.5
    while t < shown_at:
        w.on_book(t, BIDS, mid or asks or ASKS)
        t += 0.5
    w.on_book(shown_at, BIDS, after or ASKS_AFTER)
    w.tick(shown_at + 5)
    return {"totals": w.totals(shown_at + 5), "judged": judged}


def test_a_level_a_print_traded_through_reads_traded():
    got = _late_book(through={})
    assert got["totals"]["filled_shares"] == 600 and got["totals"]["pulled_shares"] == 0
    assert all(d["swept"] == 1.1 for d in got["judged"])


def test_without_the_rule_the_late_level_reads_pulled():
    got = _late_book(through={}, match=MatchParams(sweep_hold_sec=0.0))
    assert got["totals"]["pulled_shares"] == 600 and got["judged"][0]["swept"] is None


def test_prints_at_the_best_alone_prove_nothing():
    totals = _late_book()["totals"]  # 10.00 went and 10.01 shrank, 1.7 s after the prints
    assert totals["filled_shares"] == 0 and totals["pulled_shares"] == 600


@pytest.mark.parametrize("through", [
    {"conditions": "I"},          # an odd lot
    {"conditions": "O"},          # an opening cross
    {"conditions": "4 W"},        # volume only: derivatively priced, average price
    {"lit": False},               # an off-exchange report
])
def test_a_print_that_sets_no_price_on_the_book_proves_nothing(through):
    assert _late_book(through=through)["totals"]["pulled_shares"] == 600


def test_an_odd_lot_best_is_not_a_protected_quote():
    odd = [{"price": 10.00, "size": 50, "mm": "NSDQ"}, *ASKS[1:]]
    judged = _late_book(through={}, asks=odd)["judged"]
    assert all(d["swept"] is None for d in judged)


def test_a_sweep_older_than_the_hold_reaches_nothing():
    late = 1.1 + BOOK_WATCH_SWEEP_HOLD_SEC + 0.4
    assert _late_book(through={}, shown_at=late)["totals"]["pulled_shares"] == 600


def test_a_level_pulled_before_the_sweep_reached_it_still_reads_pulled():
    got = _late_book(through={}, at_best=False)  # no print at 10.00: its offer had gone
    by_price = {d["price"]: d for d in got["judged"]}
    assert by_price[10.00]["pulled"] == 500 and by_price[10.01]["filled"] == 100


def test_a_book_older_than_the_idle_limit_proves_nothing():
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, BIDS, ASKS)
    w.on_print(7.5, 10.01, 100, lit=True, conditions="")  # the last book is 6.5 s old
    assert not w.sweeps.levels


def test_new_size_posted_at_the_level_ends_the_sweep():
    # A seller posts 300 more at 10.00 after the sweep; the 800 that leaves at 2.8 may be that order, pulled.
    refilled = [{"price": 10.00, "size": 800, "mm": "NSDQ"}, *ASKS[1:]]
    by_price = {d["price"]: d for d in _late_book(through={}, mid=refilled)["judged"]}
    assert by_price[10.00]["pulled"] == 800 and by_price[10.00]["swept"] is None
    assert by_price[10.01]["filled"] == 100  # 10.01 was left as it was: its drop is the sweep's


def test_a_sweep_explains_no_more_than_the_book_showed():
    """1,500 print at 10.00 against the 500 shown (a hidden seller); the offer is shown gone at 2.4, a new
    700 is posted at 2.6 and pulled at 3.0. The 1,000 left over never fills the new order."""
    judged: list = []
    w = SymbolWatch("TEST", num_rows=10, judged=judged)
    w.on_book(1.0, BIDS, ASKS)
    w.on_print(1.1, 10.00, 1500, lit=True, conditions="")
    w.on_print(1.1, 10.01, 100, lit=True, conditions="")
    for t in (1.5, 2.0):
        w.on_book(t, BIDS, ASKS)
    w.on_book(2.4, BIDS, ASKS_AFTER)
    w.on_book(2.6, BIDS, [{"price": 10.00, "size": 700, "mm": "EDGX"}, *ASKS_AFTER])
    w.on_book(3.0, BIDS, ASKS_AFTER)
    w.tick(9.0)
    by = {(d["price"], d["t1"]): d for d in judged}
    assert by[(10.00, 2.4)]["filled"] == 500 and by[(10.00, 2.4)]["allow"] == 500
    assert by[(10.00, 3.0)]["pulled"] == 700 and by[(10.00, 3.0)]["allow"] == 0


def test_a_level_shown_gone_row_by_row_is_paid_down_to_the_size_shown():
    two_rows = [{"price": 10.00, "size": 300, "mm": "NSDQ"}, {"price": 10.00, "size": 200, "mm": "ARCA"},
                *ASKS[1:]]
    judged: list = []
    w = SymbolWatch("TEST", num_rows=10, judged=judged)
    w.on_book(1.0, BIDS, two_rows)
    w.on_print(1.1, 10.00, 900, lit=True, conditions="")
    w.on_print(1.1, 10.01, 100, lit=True, conditions="")
    w.on_book(1.6, BIDS, two_rows)
    w.on_book(2.2, BIDS, [two_rows[1], *ASKS[1:]])  # NSDQ's 300 shown gone
    w.on_book(2.8, BIDS, ASKS_AFTER)               # then ARCA's 200
    w.tick(9.0)
    at = [(d["drop"], d["allow"], d["filled"]) for d in judged if d["price"] == 10.00]
    assert at == [(300, 300, 300), (200, 200, 200)]
    assert not w.sweeps.levels.get(("ask", 10.00))  # paid in full: nothing owed there


def test_the_swept_levels_run_from_the_best_to_the_print():
    views = {"bid": side_view(BIDS, "bid", 10), "ask": side_view(ASKS, "ask", 10)}
    assert swept_levels(10.02, views) == ("ask", [10.00, 10.01, 10.02])
    assert swept_levels(10.00, views) is None  # at the best, not through it
    assert swept_levels(9.98, views) == ("bid", [9.99])


def test_the_hold_cannot_outlast_the_prints_kept():
    with pytest.raises(ValueError):
        MatchParams(sweep_hold_sec=9.0)
    with pytest.raises(ValueError):
        MatchParams(sweep_hold_sec=-1.0)


# -- the study ---------------------------------------------------------------

def _recording(tmp_path):
    """Books every half second for 200 s; at 1100.1 a buyer takes the 10.00 offer and prints through it,
    and the book shows the offer gone only at 1101.5."""
    rec = tmp_path / "2026-09-29" / "TEST"
    rec.mkdir(parents=True)
    books = []
    for i in range(401):
        t = 1000.0 + i * 0.5
        books.append({"ts": t, "bids": BIDS, "asks": ASKS if t < 1101.5 else ASKS_AFTER})
    prints = [{"ts": 1100.1, "receive_ts": 1100.1, "price": 10.00, "size": 500, "exchange": "NASDAQ", "conditions": ""},
              {"ts": 1100.1, "receive_ts": 1100.1, "price": 10.01, "size": 100, "exchange": "ARCA", "conditions": ""}]
    (rec / "l2.jsonl").write_text("\n".join(json.dumps(b) for b in books) + "\n")
    (rec / "prints.jsonl").write_text("\n".join(json.dumps(p) for p in prints) + "\n")
    return rec


def test_the_study_measures_the_rule_against_the_same_sweeps_moved(tmp_path):
    rec = window_study.read(_recording(tmp_path))
    found = sweep_study.sweeps(rec)
    assert [(s.side, s.best, sorted(s.prices)) for s in found] == [("ask", 10.00, [10.00, 10.01])]
    m = sweep_study.measure(rec)
    assert m["sweeps"] == 1 and m["levels"] == 2 and m["pulled_off"] == 600
    assert m["off"]["filled"] == 0 and m["on"]["filled"] == 600
    assert m["covered"] == {"drops": 2, "dropped": 600, "filled_off": 0, "filled_on": 600}
    # 10.00 is the best again 30-60 s either side, so the sweep moves; there it finds no drop to fill.
    # One tick beyond where it stopped, 10.02 never dropped: nothing there either.
    assert m["reach"] == {"real": 600, "matched_real": 600, "moved": 0, "beyond": 0}
