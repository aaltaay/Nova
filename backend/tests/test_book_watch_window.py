"""The book watcher's matching window (ADR 033 amendment 2026-09-30): the window as a parameter,
exact prices, and the study that measured whether a wider window would call fewer fills "pulled"."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from book_watch import window_study
from book_watch.constants_book_watch import BOOK_WATCH_MATCH_SLACK_SEC, BOOK_WATCH_SETTLE_SEC
from book_watch.detector import SymbolWatch
from book_watch.matching import DEFAULT_MATCH, MatchParams

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import book_watch_window_study  # noqa: E402


def lv(price, size):
    return {"price": price, "size": size, "mm": "NSDQ"}


ASKS = [lv(10.05, 300)]


# -- the window ---------------------------------------------------------------

def test_the_default_window_is_the_measured_half_second_either_side():
    assert DEFAULT_MATCH == MatchParams(BOOK_WATCH_MATCH_SLACK_SEC, BOOK_WATCH_MATCH_SLACK_SEC, BOOK_WATCH_SETTLE_SEC)
    assert (DEFAULT_MATCH.before_sec, DEFAULT_MATCH.after_sec, DEFAULT_MATCH.settle_sec) == (0.5, 0.5, 0.75)


def test_a_drop_is_never_judged_before_its_window_closes():
    with pytest.raises(ValueError):
        MatchParams(before_sec=0.5, after_sec=1.0, settle_sec=1.0)
    with pytest.raises(ValueError):
        MatchParams(before_sec=-0.1)


def _depth_late(match=DEFAULT_MATCH):
    """The print arrives, the book keeps showing the level for a second, then shows it gone."""
    w = SymbolWatch("TEST", num_rows=10, match=match)
    w.on_book(0.0, [lv(10.0, 500), lv(9.99, 300)], ASKS)
    w.on_print(0.2, 10.0, 500, lit=True)
    w.on_book(1.0, [lv(10.0, 500), lv(9.99, 300)], ASKS)  # the depth line has not caught up
    w.on_book(1.2, [lv(9.99, 300)], ASKS)
    w.tick(9.0)
    return w.totals(9.0)


def test_a_print_before_the_window_reads_pulled_and_a_window_that_reaches_it_fills():
    assert _depth_late()["pulled_shares"] == 500
    assert _depth_late(MatchParams(before_sec=1.0))["filled_shares"] == 500


def test_a_midpoint_print_fills_neither_level_beside_it():
    w = SymbolWatch("TEST", num_rows=10)
    w.on_book(1.0, [lv(3.65, 500), lv(3.64, 300)], [lv(3.66, 300)])
    w.on_print(1.1, 3.655, 500, lit=True)  # half a tick from both: a hidden midpoint order traded
    w.on_book(1.2, [lv(3.64, 300)], [lv(3.66, 300)])
    w.tick(5.0)
    assert w.totals(5.0)["pulled_shares"] == 500


def test_every_judged_drop_is_traced_with_the_prints_it_claimed():
    judged: list = []
    w = SymbolWatch("TEST", num_rows=10, judged=judged)
    w.on_book(1.0, [lv(10.0, 500), lv(9.99, 300)], ASKS)
    w.on_print(1.1, 10.0, 200, lit=True)
    w.on_book(1.2, [lv(9.99, 300)], ASKS)
    w.tick(5.0)
    assert len(judged) == 1
    d = judged[0]
    assert (d["t0"], d["t1"], d["side"], d["price"], d["drop"]) == (1.0, 1.2, "bid", 10.0, 500)
    assert (d["filled"], d["pulled"], d["claims"]) == (200, 300, [(1.1, 10.0, 200)])


# -- the study -----------------------------------------------------------------

BIDS_BEFORE = [lv(9.99, 1000), lv(9.98, 300), lv(9.97, 300)]
BIDS_AFTER = [lv(9.98, 300), lv(9.97, 300), lv(9.96, 300)]
ASKS_BEFORE = [lv(10.01, 300), lv(10.02, 300), lv(10.03, 300)]
ASKS_AFTER = [lv(10.02, 200), lv(10.03, 300), lv(10.04, 300)]


def _row(ts, price, size, exchange="NASDAQ", conditions=""):
    return {"ts": ts, "receive_ts": ts, "price": price, "size": size, "exchange": exchange, "conditions": conditions}


def _recording(tmp_path):
    """Books every half second for 200 s. The 9.99 bid traded 1.7 s before its book showed it (the depth
    line late), and a print through the 10.01 offer arrived 1.4 s before the book showed that offer gone."""
    rec = tmp_path / "2026-09-29" / "TEST"
    rec.mkdir(parents=True)
    books = []
    for i in range(401):
        t = 1000.0 + i * 0.5
        books.append({"ts": t, "bids": BIDS_BEFORE if t < 1060.0 else BIDS_AFTER,
                      "asks": ASKS_BEFORE if t < 1101.5 else ASKS_AFTER})
    prints = [
        _row(1058.3, 9.99, 1000),                  # the bid's own fill, early
        _row(1100.1, 10.02, 100),                  # through the 10.01 offer
        _row(1120.0, 10.01, 50, exchange="FINRA"),  # off exchange: never fills a level
        _row(1150.0, 10.0, 5000, conditions="O"),  # a cross: left out
        _row(1300.0, 10.0, 100),                   # no book within 5 s: left out
    ]
    (rec / "l2.jsonl").write_text("\n".join(json.dumps(b) for b in books) + "\n")
    (rec / "prints.jsonl").write_text("\n".join(json.dumps(p) for p in prints) + "\n")
    return rec


def test_the_study_reads_a_recording_leaving_out_crosses_and_tape_without_a_book(tmp_path):
    rec = window_study.read(_recording(tmp_path))
    assert (rec.date, rec.symbol, len(rec.books)) == ("2026-09-29", "TEST", 401)
    assert (rec.cross, rec.tape_only, len(rec.prints)) == (1, 1, 3)
    assert rec.at_quote(1058.3, 9.99) == "bid" and rec.at_quote(1100.1, 10.02) is None


def test_the_sweep_fills_the_early_prints_only_once_the_window_reaches_them(tmp_path):
    swept, judged = window_study.sweep(window_study.read(_recording(tmp_path)))
    assert [swept[w]["dropped"] for w in ("0.5", "1", "2", "3")] == [1400, 1400, 1400, 1400]
    assert [swept[w]["filled"] for w in ("0.5", "1", "2", "3")] == [0, 100, 1100, 1100]
    assert sorted((d["price"], d["pulled"]) for d in judged) == [(9.99, 1000), (10.01, 300), (10.02, 100)]


def test_what_a_wider_window_adds_is_weighed_against_the_same_prints_moved(tmp_path):
    m = window_study.measure(window_study.read(_recording(tmp_path)))
    ext = m["extension"]
    assert ext["pulled"] == 1400
    assert [ext["before"][s]["real"] for s in ("1", "2", "3")] == [100, 1100, 1100]
    assert [ext["after"][s]["real"] for s in ("1", "2", "3")] == [0, 0, 0]
    # Moved 30-60 s, the prints land where no drop was pulled at their price: nothing by chance.
    assert ext["before"]["2"]["moved_real"] == 1100 and ext["before"]["2"]["moved"] == 0
    # The unclaimed bid print had its own drop shown 1.7 s after it.
    ev = m["evidence"]
    assert ev["real"]["volume"] == 1000 and ev["real"]["print_early_1_3"] == 1000
    assert ev["moved"]["print_early_1_3"] == 0
    # The print through the offer: the book showed the offer gone 1.4 s later.
    assert m["depth_late"] == {"through": 1, "<=0.5": 0, "0.5-1": 0, "1-3": 1, "3-10": 0, "never": 0}


def test_the_answer_adds_recordings_up_by_day_and_in_all(tmp_path):
    one = window_study.read(_recording(tmp_path / "a"))
    two = window_study.read(_recording(tmp_path / "b"))
    answer = window_study.study([(one, window_study.measure(one)), (two, window_study.measure(two))])
    assert answer["schema_version"] == 1 and answer["windows_sec"] == [0.5, 1.0, 2.0, 3.0]
    assert len(answer["recordings"]) == 2 and answer["recordings"][0]["left_out"] == {"cross": 1, "tape_only": 1}
    assert answer["by_day"]["2026-09-29"]["sweep"]["2"]["filled"] == 2200
    assert answer["total"]["depth_late"]["through"] == 2
    text = book_watch_window_study.render(answer, by_recording=True)
    assert "09-29 TEST" in text and "before 1s adds" in text and "Depth late" in text
