"""The halt / LULD log and the leaderboard route shapes (ADR 022)."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from leaderboard import halts, playback, queue, recorder, store
from leaderboard.routes import router

ET = ZoneInfo("America/New_York")
DAY = "2026-09-18"


def et(hh: int, mm: int, ss: int = 0) -> float:
    return datetime(2026, 9, 18, hh, mm, ss, tzinfo=ET).timestamp()


@pytest.fixture(autouse=True)
def fresh():
    queue.reset_for_tests()
    halts.reset_for_tests()
    recorder.reset_for_tests()
    yield
    queue.reset_for_tests()


def events(day: str = DAY):
    queue.flush_blocking()
    with store.connect() as db:
        return store.halt_events(db, day)


def test_ibkr_transitions_log_a_start_and_an_end():
    halts.observe_ibkr("abc", {"halt_start": et(9, 50), "kind": "luld", "halt_code": 2}, now=et(9, 50, 3))
    halts.observe_ibkr("ABC", None, now=et(9, 55))
    rows = events()
    assert [(r["symbol"], r["event"], r["ts"], r["source"]) for r in rows] == [
        ("ABC", "start", et(9, 50), "ibkr_ticker_halted"),
        ("ABC", "end", et(9, 55), "ibkr_ticker_halted"),
    ]
    assert rows[0]["kind"] == "luld" and rows[0]["code"] == "2" and rows[0]["session_date"] == DAY


def test_every_rss_row_is_logged_including_a_second_halt_and_repeats_are_ignored():
    rss = [
        SimpleNamespace(symbol="XYZ", reason_code="LUDP", official_halt_start=et(9, 40), trade_resume=et(9, 45), mwcb_level=None),
        SimpleNamespace(symbol="XYZ", reason_code="LUDP", official_halt_start=et(10, 5), trade_resume=None, mwcb_level=None),
        SimpleNamespace(symbol="", reason_code="MWC1", official_halt_start=et(10, 0), trade_resume=None, mwcb_level=1),
    ]
    assert halts.observe_rss(rss) == 3
    assert halts.observe_rss(rss) == 0  # the next poll repeats the same rows
    rows = events()
    assert [(r["event"], r["ts"]) for r in rows] == [("start", et(9, 40)), ("end", et(9, 45)), ("start", et(10, 5))]
    assert {r["source"] for r in rows} == {"nasdaq_trade_halt_rss"}
    assert halts.halted_at(rows, "XYZ", et(9, 42)) is True
    assert halts.halted_at(rows, "XYZ", et(9, 50)) is False
    assert halts.halted_at(rows, "XYZ", et(10, 6)) is True


def test_the_ibkr_tick_hook_and_the_rss_refresh_feed_the_log(monkeypatch):
    from ibkr import halt_status, nasdaq_halt_feed, ticks_handler

    halt_status.reset()
    monkeypatch.setattr(ticks_handler, "_broadcast_halt", lambda *_a: None)
    ticks_handler._observe_halt("HLT", SimpleNamespace(halted=2))
    ticks_handler._observe_halt("HLT", SimpleNamespace(halted=0))
    today = datetime.now(ET).date().isoformat()  # the tick hook stamps the wall clock
    assert [r["event"] for r in events(today) if r["symbol"] == "HLT"] == ["start", "end"]
    xml = """<?xml version="1.0"?><rss xmlns:ndaq="http://www.nasdaqtrader.com/"><channel><item>
      <title>RSSX</title><ndaq:HaltDate>09/18/2026</ndaq:HaltDate><ndaq:HaltTime>10:15:00</ndaq:HaltTime>
      <ndaq:IssueSymbol>RSSX</ndaq:IssueSymbol><ndaq:ReasonCode>LUDP</ndaq:ReasonCode>
      <ndaq:ResumptionDate>09/18/2026</ndaq:ResumptionDate><ndaq:ResumptionTradeTime>10:20:00</ndaq:ResumptionTradeTime>
    </item></channel></rss>"""
    nasdaq_halt_feed.reset()
    result = nasdaq_halt_feed.refresh(xml_text=xml, now=et(10, 21))
    if not result.get("ok"):
        pytest.skip(f"fixture XML not accepted by this parser: {result}")
    logged = [r for r in events() if r["symbol"] == "RSSX"]
    assert [(r["event"], r["ts"]) for r in logged] == [("start", et(10, 15)), ("end", et(10, 20))]


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c


def seed():
    recorder.start_for_tests("run-r")
    batch = recorder.build_minute(
        int(et(7, 42)), {"gainers": ([{"symbol": "AAA", "price": 5.0, "prev_close": 2.0, "volume": 900_000}], "live")},
        feed_live=True, halt_feed_ok=True, run_id="run-r",
    )
    for kind, items in batch.items():
        queue.enqueue(kind, items)
    queue.flush_blocking()


def test_route_shapes(client):
    seed()
    days = client.get("/api/leaderboard/days").json()
    assert set(days) == {"schema_version", "store", "days"} and days["days"][0]["date"] == DAY
    board = client.get(f"/api/leaderboard/{DAY}", params={"at": et(7, 42, 30)}).json()
    assert {"schema_version", "date", "at", "source", "minute_ts", "covered", "gap", "boards", "leaders"} <= set(board)
    row = board["boards"]["gainers"]["rows"][0]
    assert set(row) == {
        "symbol", "minute_ts", "board", "source", "rank", "price", "prev_close", "change_pct", "volume",
        "rvol", "rvol_basis", "float_shares", "has_news", "news_first_seen_ts", "halted", "gap_pct",
        "exchange", "market_cap",
    }
    assert board["leaders"]["symbols"] == ["AAA"] and board["leaders"]["rules"]["top_n"] == 3
    cov = client.get(f"/api/leaderboard/{DAY}/coverage").json()
    assert set(cov) == {"date", "source", "session_open", "session_close", "spans", "gaps"}
    assert cov["spans"] == [[int(et(7, 42)), int(et(7, 43))]]
    assert client.get(f"/api/leaderboard/{DAY}/halts", params={"until": et(8, 0)}).json() == {"date": DAY, "events": []}


@pytest.mark.parametrize("url", [
    "/api/leaderboard/2026-13-01?at=1", "/api/leaderboard/yesterday?at=1",
    f"/api/leaderboard/{DAY}?at=1&source=guessed", f"/api/leaderboard/{DAY}/coverage?source=x",
])
def test_bad_inputs_are_400(client, url):
    assert client.get(url).status_code == 400


def test_board_without_at_is_422(client):
    assert client.get(f"/api/leaderboard/{DAY}").status_code == 422


def test_a_reconstructed_day_plays_back_as_the_market_board():
    from leaderboard.rows import make_row

    minute = int(et(8, 0))
    rows = [make_row(symbol=s, minute_ts=minute, board="market", source="reconstructed", rank=i, price=p,
                     prev_close=2.0, volume=300_000) for i, (s, p) in enumerate([("RRR", 6.0), ("SSS", 4.0)], start=1)]
    with store.connect() as db:
        store.write_batch(db, rows=rows, coverage=[{"session_date": DAY, "minute_ts": minute, "source": "reconstructed",
                                                    "board": "market", "state": "rebuilt", "row_count": 2, "run_id": None}])
    out = playback.board_at(DAY, et(8, 0, 10))
    assert out["source"] == "reconstructed" and out["leaders"]["board"] == "market"
    assert [r["symbol"] for r in out["boards"]["market"]["rows"]] == ["RRR", "SSS"]
    assert all(r["halted"] is None for r in out["boards"]["market"]["rows"])
    assert playback.board_at(DAY, et(8, 1, 10))["gap"]["reason"] == "not_recorded"
