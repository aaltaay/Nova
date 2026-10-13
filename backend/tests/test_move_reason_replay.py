"""Why it's moving on a Sim replay desk: the replayed day's facts as of the playhead, never later (ADR 028).

Verified 2026-10-12: the Sim on SDEV 2026-10-02 showed "Not a big move today (-3.9%)" -- the wall clock's
day. The replay here is a real historical window in a private Sim store (the IBKR download path), and every
record the read takes a fact from holds one row before the playhead and one after it: the read must show the
first and never the second.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from catalysts import feed_store
from catalysts.recorded import covered_sources, verdict_at
from leaderboard import store as lb_store
from main import app
from move_reason import borrow_feed, borrow_store, rules
from move_reason import facts as facts_mod
from move_reason import short_interest
from sim import session_clock as clock
from sim.mode import set_venue
from tests.test_bot_sim_replay import DAY, SYM, go, load_window
from tests.test_sim_practice import isolated  # noqa: F401 -- autouse: a private Sim store and clean replay

client = TestClient(app)
ET = ZoneInfo("America/New_York")


def et(hh: int, mm: int, ss: int = 0, day: str = DAY) -> float:
    d = date.fromisoformat(day)
    return datetime(d.year, d.month, d.day, hh, mm, ss, tzinfo=ET).timestamp()


PLAYHEAD = et(7, 1, 15)   # go(75) on the 07:00 window


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """Private record stores, the borrow feed on over a private borrow record, and today's read forbidden."""
    for env, name in (("NOVA_LEADERBOARD_DIR", "lb"), ("NOVA_CATALYST_DIR", "cat"), ("NOVA_MARKET_DATA_DIR", "massive")):
        monkeypatch.setenv(env, str(tmp_path / name))
    monkeypatch.setenv("NOVA_BORROW_FEED", "1")
    feed = borrow_feed.BorrowFeed(db=borrow_store.connect(tmp_path / "borrow.sqlite3"))
    monkeypatch.setattr(borrow_feed, "_feed", feed)

    def today(*a, **k):
        raise AssertionError("today's facts were gathered on a replay desk")

    monkeypatch.setattr(facts_mod, "gather", today)
    return tmp_path


def _board(minute: float, *, float_shares: float, price: float) -> None:
    row = {"session_date": DAY, "minute_ts": int(minute), "source": "recorded", "board": "gainers", "symbol": SYM,
           "rank": 1, "price": price, "prev_close": 8.0, "change_pct": price / 8.0 - 1, "volume": 2_000_000,
           "rvol": 8.5, "rvol_basis": "daily_avg", "float_shares": float_shares, "float_contradicted": 0}
    with lb_store.connect() as db:
        lb_store.write_batch(
            db, rows=[row],
            coverage=[{"session_date": DAY, "minute_ts": int(minute), "source": "recorded", "board": "gainers",
                       "state": "live", "row_count": 1, "run_id": "r1"}],
            minutes=[{"session_date": DAY, "minute_ts": int(minute), "run_id": "r1", "feed_live": 1,
                      "halt_feed_ok": 1}])


def _halt(ts: float) -> None:
    with lb_store.connect() as db:
        lb_store.write_batch(db, halts=[{"symbol": SYM, "ts": ts, "event": "start", "kind": "LUDP", "code": "LUDP",
                                         "source": "nasdaq_trade_halt_rss", "session_date": DAY, "recorded_ts": ts}])


def _finra(month: str, *rows: tuple[str, int, float]) -> None:
    folder = short_interest.directory()
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / f"{month}.jsonl").open("a", encoding="utf-8") as fh:
        for settled, shares, dtc in rows:
            fh.write(json.dumps({"settlement_date": settled, "ticker": SYM, "short_interest": shares,
                                 "avg_daily_volume": 1000, "days_to_cover": dtc}) + "\n")


def _news(item_id: str, ts: float, title: str, *, spans: tuple[float, float] | None = None) -> None:
    db = feed_store.connect()
    try:
        feed_store.put_items(db, [{"item_id": item_id, "source": "globenewswire", "published_ts": ts, "title": title,
                                   "tickers": [SYM]}])
        if spans:
            for source in ("edgar", "globenewswire", "prnewswire", "newsfile"):
                feed_store.put_span(db, source, *spans)
    finally:
        db.close()


def _poll(ts: float, available: int | None, fee: float | None = 12.0) -> None:
    value = ({"listed": True, "fee_rate": fee, "rebate_rate": None, "available": available, "capped": False}
             if available is not None else {"listed": False, "fee_rate": None, "rebate_rate": None,
                                            "available": None, "capped": False})
    borrow_store.put_poll(borrow_feed.get_feed()._db, ts, ts - 60, 1, [(SYM, value)])


def _replay() -> dict:
    set_venue("sim", persist=False)
    load_window()
    go(75)
    res = client.get(f"/api/why/{SYM.lower()}")
    assert res.status_code == 200
    return res.json()


def test_a_replay_reads_its_own_day_as_of_the_playhead(stores):
    _board(et(7, 1), float_shares=480_216, price=11.5)
    _board(et(7, 2), float_shares=9_999_999, price=14.0)          # one minute after the playhead
    _halt(et(7, 0, 30))
    _halt(et(7, 30))                                               # after the playhead
    _finra("2026-08", ("2026-08-31", 13_000, 1.0))                 # counts from Sep 11
    _finra("2026-09", ("2026-09-15", 200_000, 9.0))                # counts from Sep 25: not yet on Sep 18
    _news("before", et(6, 0), "IMCC to Present at an Investor Conference",
          spans=(et(15, 0, day="2026-09-17"), et(8, 0)))
    _news("after", et(7, 30), "IMCC Receives FDA Approval for Its Lead Drug")
    _poll(et(4, 5), 40_000)
    _poll(et(7, 0), 5_000)
    _poll(et(7, 15), None)                                         # nothing to lend -- after the playhead

    body = _replay()

    assert (body["symbol"], body["replay"], body["session_date"]) == (SYM, True, DAY)
    assert body["generated_at"] == clock.now_et().timestamp() == PLAYHEAD
    by = {c["id"]: c for c in body["checks"]}
    assert all(c["as_of"] is None or c["as_of"] <= PLAYHEAD for c in body["checks"])
    # The replay's own last print against its previous close; the board at 07:01, never 07:02.
    assert body["facts"]["price"] == 12.0 and body["facts"]["change_pct"] == pytest.approx(0.5)
    assert by["float"]["value"] == "480K shares -- low float" and by["float"]["as_of"] == et(7, 1)
    assert by["float"]["source"].startswith("Yahoo float as Nova's recorded board held it at 07:01 ET")
    assert by["volume"]["value"] == "RVOL 8.5x"
    # FINRA's Aug 31 settlement -- Sep 15's was not published by Sep 18 -- with FINRA's own days to cover.
    assert by["short_interest"]["value"] == "2.7% of float · 1.0 days to cover (FINRA)"
    assert "FINRA settlement Aug 31" in by["short_interest"]["detail"]
    assert "the Sep 15 settlement counts from Sep 25" in by["short_interest"]["detail"]
    # The borrow at the 07:00 poll, the day's first at 04:05; the 07:15 "nothing to lend" is after it.
    assert by["borrow"]["value"] == "Fee 12.0%/yr · 5K shares to lend" and by["borrow"]["as_of"] == et(6, 59)
    assert by["borrow"]["detail"] == "lendable 40K -> 5K since 04:05 ET"
    # Only the conference item was out by 07:01; the FDA approval at 07:30 is not read.
    assert by["news"]["state"] == "no" and by["news"]["value"] == "Routine company item only"
    assert by["halts"]["value"] == "LULD pause 1x"
    assert "Nova's halt log for Sep 18 up to 07:01 ET, and the exchange day before it" == by["halts"]["source"]


def test_a_replay_older_than_the_borrow_record_reads_borrow_unknown_with_the_reason(stores):
    _board(et(7, 1), float_shares=480_216, price=11.5)
    _poll(et(9, 0, day="2026-09-28"), 5_000)

    body = _replay()

    borrow = {c["id"]: c for c in body["checks"]}["borrow"]
    assert (borrow["state"], borrow["value"]) == ("unknown", "Not recorded")
    assert borrow["detail"] == ("Nova's borrow record starts Sep 28 09:00 ET (it keeps 14 days); "
                                "Sep 18 07:01 is before it")


def test_a_replay_no_record_reaches_is_not_read(stores):
    body = _replay()

    assert (body["replay"], body["likely"]["kind"]) == (True, "not_read")
    assert body["likely"]["label"] == "Not read on a Sim replay of Sep 18"
    assert body["likely"]["detail"].startswith("Nothing Nova recorded reaches this moment")
    assert body["checks"] == [] and body["facts"] == {}


def test_a_settlement_published_after_the_playhead_is_never_used(stores):
    sym = "SDEV"
    folder = short_interest.directory()
    folder.mkdir(parents=True)
    (folder / "2026-09.jsonl").write_text("\n".join(json.dumps(r) for r in (
        {"settlement_date": "2026-09-15", "ticker": sym, "short_interest": 1_212_152, "days_to_cover": 4.4},
        {"settlement_date": "2026-09-30", "ticker": sym, "short_interest": 3_436_239, "days_to_cover": 1.0},
    )) + "\n", encoding="utf-8")

    assert short_interest.counts_from(date(2026, 9, 15)) == date(2026, 9, 25)
    assert short_interest.counts_from(date(2026, 9, 30)) == date(2026, 10, 12)
    oct2 = short_interest.published_at(sym, et(10, 31, day="2026-10-02"))
    assert oct2["row"]["short_interest"] == 1_212_152
    assert oct2["pending"] == {"settlement_date": date(2026, 9, 30), "counts_from": date(2026, 10, 12)}
    oct9 = short_interest.published_at(sym, et(15, 59, day="2026-10-09"))
    assert oct9["row"]["short_interest"] == 1_212_152            # published about Oct 9, after the close
    assert short_interest.published_at(sym, et(9, 30, day="2026-10-12"))["row"]["short_interest"] == 3_436_239
    assert short_interest.published_at(sym, et(10, 0, day="2026-09-24"))["row"] is None


def test_news_published_after_the_playhead_never_counts(stores):
    at = et(9, 45)
    _news("on-the-second", at, "IMCC Receives FDA Approval for Its Lead Drug", spans=(et(15, 0, day="2026-09-17"), at))
    _news("a-second-later", at + 1, "IMCC Announces a $50 Million Registered Direct Offering")

    v = verdict_at(SYM, at)
    assert (v["verdict"], v["category"], v["n_items"]) == ("catalyst", "fda_regulatory", 1)
    assert verdict_at(SYM, at - 1)["verdict"] == "none_found"


def test_coverage_spans_that_overlap_join_and_a_gap_inside_the_window_breaks_them():
    spans = [("edgar", 0, 50), ("edgar", 40, 120), ("globenewswire", 0, 50), ("globenewswire", 60, 120),
             ("prnewswire", 20, 120), ("newsfile", -100, -50), ("newsfile", 15, 120)]
    assert covered_sources(spans, 10, 100) == ["edgar"]
    assert covered_sources(spans, 30, 100) == ["edgar", "prnewswire", "newsfile"]


def test_a_replay_note_names_the_source_the_as_of_and_why_a_fact_is_unknown():
    facts = {"change_pct": 0.5, "borrow": None, "days_to_cover": 4.4, "days_to_cover_by": "FINRA",
             "check_notes": {"borrow": {"source": "Recorded borrow", "unknown_value": "Not recorded",
                                        "note": "Before the record"},
                             "float": {"source": "Board float", "as_of": 123.0, "note": "No board row"}}}
    by = {c["id"]: c for c in rules.read(facts, 200.0)["checks"]}
    assert (by["borrow"]["value"], by["borrow"]["detail"], by["borrow"]["source"]) == (
        "Not recorded", "Before the record", "Recorded borrow")
    assert (by["float"]["state"], by["float"]["as_of"], by["float"]["detail"]) == ("unknown", 123.0, "No board row")
    assert by["short_interest"]["value"] == "4.4 days to cover (FINRA)"


def test_the_live_desk_still_reads(monkeypatch):
    seen = []

    def gather(symbol, now=None):
        seen.append(symbol)
        return {"symbol": symbol, "change_pct": 0.032}

    monkeypatch.setattr(facts_mod, "gather", gather)
    set_venue("paper", persist=False)

    body = client.get(f"/api/why/{SYM}").json()

    assert seen == [SYM] and body["replay"] is False
    assert body["likely"]["label"] == "Not a big move today (+3.2%)"


def test_a_batch_on_a_replay_reads_the_board_once_and_matches_the_single_read(stores, monkeypatch):
    """The Catalyst column's batch (`GET /api/why?symbols=...&board=...`) on a replay: one board read and one halt-log
    read for every symbol (PR #886 review), and each symbol's read is the single route's."""
    from leaderboard import playback

    _board(et(7, 1), float_shares=480_216, price=11.5)
    _halt(et(7, 0, 30))
    _poll(et(7, 0), 5_000)
    single = _replay()
    calls = []
    real = playback.board_at
    monkeypatch.setattr(playback, "board_at", lambda *a, **k: calls.append(a) or real(*a, **k))

    res = client.get(f"/api/why?symbols={SYM},ZZZZ&board=gainers")

    assert res.status_code == 200
    body = res.json()
    assert (body["replay"], body["errors"], len(calls)) == (True, {}, 1)
    read = body["reads"][SYM]
    assert (read["facts"]["priced_by"], read["facts"]["board"]) == ("replay", "gainers")
    assert read["likely"] == single["likely"] and read["checks"] == single["checks"]
    alone = client.get("/api/why/ZZZZ").json()
    assert body["reads"]["ZZZZ"]["likely"] == alone["likely"]
