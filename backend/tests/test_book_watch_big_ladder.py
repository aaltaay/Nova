"""Big sellers and buyers on the Level 2 ladder (#984): pulled as the price came, back again, the seconds of
lit volume, and the depth socket's frames that carry them with the float."""
from __future__ import annotations

import pytest

from book_watch import ladder, live
from book_watch.constants_book_watch import BOOK_WATCH_SIDES_PUSH_SEC
from book_watch.detector import SymbolWatch
from book_watch.pace import LitPace


def lv(price, size, mm="NSDQ"):
    return {"price": price, "size": size, "mm": mm}


BIDS = [lv(4.46, 500), lv(4.45, 600), lv(4.44, 700), lv(4.43, 400)]


def asks(wall=20_000, at=4.50):
    rows = [lv(4.48, 500), lv(4.49, 400), lv(4.51, 800), lv(4.52, 600)]
    return rows + [lv(at, wall)] if wall else rows


def bigs(events):
    return [e for e in events if e["event"] == "big"]


def called(w, start=1.0, last=4.47):
    """A print at ``last``, then the wall on every book from ``start`` until it is called."""
    w.on_print(start - 0.5, last, 100, lit=True)
    out = []
    for i in range(4):
        out += w.on_book(start + i, BIDS, asks())
    assert [e["state"] for e in bigs(out)] == ["holding"]
    return bigs(out)[0]


# -- pulled as the price came -----------------------------------------------------------

def test_a_wall_pulled_as_the_price_came_closer_says_so():
    w = SymbolWatch("TEST", num_rows=10)
    big = called(w)
    assert big["distance_called"] == pytest.approx(0.03) and big["on_approach"] is None
    w.on_print(5.0, 4.49, 300, lit=True)              # the price walks up to it
    w.on_book(6.0, BIDS, asks(0))
    (out,) = bigs(w.tick(7.0))
    assert out["state"] == "pulled" and out["on_approach"] is True


def test_a_wall_pulled_while_the_price_stood_is_not_on_approach():
    w = SymbolWatch("TEST", num_rows=10)
    called(w)
    w.on_book(6.0, BIDS, asks(0))
    (out,) = bigs(w.tick(7.0))
    assert out["state"] == "pulled" and out["on_approach"] is False


def test_a_taken_wall_has_no_approach_word():
    w = SymbolWatch("TEST", num_rows=10)
    called(w)
    (out,) = bigs(w.on_print(5.0, 4.51, 200, lit=True))
    assert out["state"] == "eaten" and out["on_approach"] is None


# -- back again -----------------------------------------------------------------------

def test_a_wall_called_where_one_was_pulled_says_it_is_back():
    w = SymbolWatch("TEST", num_rows=10)
    called(w)
    w.on_book(6.0, BIDS, asks(0))
    w.tick(7.0)                                        # pulled, ended at 6.0
    out = []
    for t in (8.0, 9.0, 10.0, 11.0):
        out += w.on_book(t, BIDS, asks(18_000))
    (again,) = bigs(out)
    assert again["state"] == "holding"
    assert again["back"] == {"pulled": 1, "last_ended_ts": 6.0, "last_size": 20_000}


def test_a_first_wall_and_one_long_after_a_pull_are_not_back():
    w = SymbolWatch("TEST", num_rows=10)
    assert called(w)["back"] is None
    w.on_book(6.0, BIDS, asks(0))
    w.tick(7.0)
    out = []
    for t in (400.0, 401.0, 402.0, 403.0):            # past the 300 s
        out += w.on_book(t, BIDS, asks())
    assert bigs(out)[0]["back"] is None


# -- how fast it trades -------------------------------------------------------------------

def test_the_pace_counts_lit_trades_odd_lots_too_and_never_crosses_or_dark_prints():
    pace = LitPace(window_sec=60, min_sec=10)
    pace.on_print(0.5, 999, lit=True, conditions="")      # before any book: not watching yet
    pace.on_book(1.0)
    pace.on_print(2.0, 1_000, lit=True, conditions="")
    pace.on_print(3.0, 50, lit=True, conditions="I")      # an odd lot is trading
    pace.on_print(4.0, 5_000, lit=False, conditions="")   # off the lit book
    pace.on_print(5.0, 9_000, lit=True, conditions="Q")   # a cross
    assert pace.rate(8.0) == (None, None)                 # under 10 s of watching
    got, per_sec = pace.rate(11.0)
    assert got == {"window_sec": 10.0, "lit_shares": 1_050} and per_sec == pytest.approx(105.0)
    assert pace.rate(100.0) == ({"window_sec": 60.0, "lit_shares": 0}, None)
    pace.reset()
    assert pace.rate(200.0) == (None, None)


def test_each_wall_says_how_long_the_last_minutes_lit_volume_would_take_to_trade_it():
    w = SymbolWatch("TEST", num_rows=10)
    called(w)
    w.on_print(4.5, 4.48, 4_000, lit=True)
    reading = w.big.reading(11.0)                          # 10 s since the first book
    assert reading["pace"] == {"window_sec": 10.0, "lit_shares": 4_000}
    assert reading["sellers"][0]["clear_sec"] == pytest.approx(50.0)  # 20,000 / 400 a second


def test_an_ended_wall_has_no_clear_time():
    w = SymbolWatch("TEST", num_rows=10)
    called(w)
    w.on_print(4.5, 4.48, 4_000, lit=True)
    w.on_print(5.0, 4.51, 200, lit=True)
    assert w.big.reading(11.0)["sellers"][0]["clear_sec"] is None


# -- the depth socket -----------------------------------------------------------------------

@pytest.fixture
def worker_on(monkeypatch):
    monkeypatch.setenv("NOVA_BOOK_WATCH", "1")
    monkeypatch.setenv("NOVA_BOOK_WATCH_JOURNAL", "0")
    monkeypatch.setattr(live, "_ensure_thread", lambda: None)
    live.reset_for_tests()
    yield
    live.reset_for_tests()


@pytest.fixture
def float_cached(monkeypatch):
    import fundamentals

    rows = {"AAPL": {"float_shares": 2_500_000, "float_contradicted": False}}
    monkeypatch.setattr(fundamentals, "peek_cached", lambda s: dict(rows[s]) if s in rows else None)
    return rows


def _wall_live(symbol="AAPL"):
    live.process(("print", symbol, 0.5, 4.47, 100, True, ""))
    for i in range(4):
        live.process(("book", symbol, 1.0 + i, BIDS, asks()))


def test_the_socket_carries_each_big_seller_and_the_float(worker_on, float_cached):
    _wall_live()
    push = ladder.LadderPush("aapl")
    first = push.frame(4.5)
    assert first["reset"] is True and first["big_float"] == {"shares": 2_500_000.0, "contradicted": False}
    (big,) = first["big"]
    assert big["kind"] == "big_seller" and big["price"] == 4.50 and big["state"] == "holding"
    # A wall that holds is sent again no faster than the sides' clock, for its seconds of volume.
    assert push.frame(4.5 + BOOK_WATCH_SIDES_PUSH_SEC / 2) is None
    again = push.frame(4.5 + BOOK_WATCH_SIDES_PUSH_SEC)
    assert again is not None and again["big"][0]["id"] == big["id"]


def test_a_change_to_the_wall_is_sent_at_once_and_its_end_too(worker_on, float_cached):
    _wall_live()
    push = ladder.LadderPush("AAPL")
    push.frame(4.5)
    live.process(("print", "AAPL", 4.6, 4.50, 3_000, True, ""))
    hit = push.frame(4.7)
    assert hit["big"][0]["traded"] == 3_000
    live.process(("print", "AAPL", 4.8, 4.51, 200, True, ""))
    gone = push.frame(4.9)
    assert gone["big"][0]["state"] == "eaten"
    assert push.frame(5.0) is None                     # nothing holds and nothing changed


def test_no_float_cached_reads_none_and_a_contradicted_one_says_so(worker_on, float_cached):
    assert ladder.big_float("ZZZZ") is None
    float_cached["TINY"] = {"float_shares": 900_000, "float_contradicted": True}
    assert ladder.big_float("TINY") == {"shares": 900_000.0, "contradicted": True}
    float_cached["NONE"] = {"float_shares": None}
    assert ladder.big_float("NONE") is None


def test_an_absent_frame_clears_the_big_sellers(worker_on, float_cached):
    _wall_live()
    frame = ladder.LadderPush("AAPL").frame(4.5, live_line=False)
    assert frame["watching"] is False and frame["big"] == [] and frame["big_float"] is None


# -- the study ---------------------------------------------------------------------------------

def _recording(tmp_path):
    """A seller of 20,000 at 4.50 over a 4.47 price for 30 s, pulled; then the book sits 5 cents lower."""
    import json

    rec = tmp_path / "2026-10-14" / "XYZ"
    rec.mkdir(parents=True)
    low_bids = [lv(round(r["price"] - 0.05, 2), r["size"]) for r in BIDS]
    low_asks = [lv(round(r["price"] - 0.05, 2), r["size"]) for r in asks(0)]
    books = [{"ts": 1000.0 + i, "bids": BIDS if i < 30 else low_bids, "asks": asks() if i < 30 else low_asks}
             for i in range(100)]
    prints = [{"ts": 999.5, "receive_ts": 999.5, "price": 4.47, "size": 100, "exchange": "NASDAQ", "conditions": ""}]
    (rec / "l2.jsonl").write_text("\n".join(json.dumps(b) for b in books) + "\n")
    (rec / "prints.jsonl").write_text("\n".join(json.dumps(p) for p in prints) + "\n")
    return rec


def test_the_study_measures_each_wall_from_its_call_and_its_end(tmp_path):
    from book_watch import big_study

    br = big_study.read(_recording(tmp_path))
    (ev,) = big_study.events(br)
    assert ev["side"] == "ask" and ev["price"] == 4.50 and ev["ended"] == "pulled" and ev["on_approach"] is False
    assert ev["at"] == 1003.0 and ev["ended_at"] == 1030.0
    flush = ev["from_call"]["60"]["flush_bp"]
    assert flush == pytest.approx((4.47 - 4.42) / 4.47 * 1e4)       # the mid fell 5 cents: toward a flush
    assert ev["from_call"]["60"]["broke"] is False and "300" not in ev["from_call"]  # past the recording
    assert ev["from_end"]["10"]["flush_bp"] == pytest.approx(0.0)  # it was already lower when it left
    answer = big_study.study([br])
    pulled = answer["groups"]["ask"]["by_end"]["pulled"]["from_call"]
    assert pulled["n"] == 1 and pulled["horizons"]["60"]["flushed_pct"] == 100.0
    assert answer["groups"]["bid"]["all"]["n"] == 0 and answer["schema_version"] == 1
    assert answer["baseline_seller"]["10"]["flush_bp"]["n"] >= 1


def test_the_study_never_holds_a_wall_across_a_recording_gap(tmp_path):
    """Shown at 1000-1001, the recorder down, shown again from 1100: without the restart the tracker reads it as
    held for 100 s and calls it; with it, the hold starts again after the gap."""
    import json
    from datetime import datetime, timezone

    from book_watch import big_study
    from book_watch.hidden_study import recording_restarts

    rec = tmp_path / "2026-10-14" / "XYZ"
    rec.mkdir(parents=True)
    books = [{"ts": t, "bids": BIDS, "asks": asks()} for t in (1000.0, 1001.0, 1100.0, 1101.0)]
    prints = [{"ts": 999.5, "receive_ts": 999.5, "price": 4.47, "size": 100, "exchange": "NASDAQ", "conditions": ""}]
    (rec / "l2.jsonl").write_text("\n".join(json.dumps(b) for b in books) + "\n")
    (rec / "prints.jsonl").write_text("\n".join(json.dumps(p) for p in prints) + "\n")

    def iso(t):
        return datetime.fromtimestamp(t, timezone.utc).isoformat()

    manifest = {"segments": [{"started_et": iso(999.0), "stopped_et": iso(1002.0)},
                             {"started_et": iso(1100.0), "stopped_et": iso(1102.0)}]}
    restarts = recording_restarts(manifest, rec)
    assert restarts == [1100.0]
    assert [w["called_ts"] for w in big_study.read(rec).called] == [1100.0]
    assert big_study.read(rec, restarts=restarts).called == []
