"""A ticker the feed read glued to its price, checked against IBKR's tape at the entry (followed traders, 2026-10-14).

With no space between a ticker and its price on the stream's bar, OCR can take the ticker's last letter for a digit:
the live feed read "SOFI 14.03" as SOF 114.03. When the ticker one letter shorter is a real stock trading near the true
one's price, a position read glued from first frame to last is priced against it: here XYZ, a made-up stock near $14,
for the bar's "XYZI 14.03" read XYZ 114.03 -- a gain of 87% that never happened. Synthetic trades and tapes only.
Schema: architecture/schema/followed-traders.md ("A ticker glued to its price").
"""
from __future__ import annotations

import asyncio
import copy
import json
import time
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from followed_traders import exits, feed, lines, routes, tickers, view
from followed_traders.constants_followed import FOLLOWED_FEED_URL_ENV, FOLLOWED_NO_SUCH_TICKER

BASE = "http://127.0.0.1:8787"
DATE = "2026-10-13"


def _ts(clock: str, date: str = DATE) -> str:
    return f"{date}T{clock}-04:00"


def _epoch(clock: str, date: str = DATE) -> float:
    return datetime.fromisoformat(_ts(clock, date)).timestamp()


def _trade(symbol="XYZ", entry=114.03, *, trader="ALPHA", side="short", price=None, entry_clock="10:00:00",
           status="open", exit_clock=None, adds=(), read_as=None):
    return {
        "trader": trader, "side": side, "symbol": symbol, "entry_price": entry,
        "price": entry if price is None else price, "entry_ts": _ts(entry_clock), "entry_since_ts": None,
        "entry_known": True, "adds": [{"ts": _ts(c), "price": p, "prev_price": q} for c, p, q in adds],
        "exit_ts": _ts(exit_clock) if exit_clock else None, "exit_since_ts": None, "status": status,
        "entry_evidence": None, "exit_evidence": None, "read_as": read_as,
    }


def _day(trades, date=DATE, today=DATE):
    return {"date": date, "today": today, "dates": [date],
            "status": {"video": {"id": "x", "title": "Afternoon show"}, "live": True, "clock": "15:00:00",
                       "updated_at": _ts("15:00:02", today), "bar_visible": True, "traders": ["ALPHA"],
                       "positions": {}},
            "trades": trades}


def _at(price):
    return exits.stated("at", price=price, trade_ts=1.0, to_ts=2.0, source="ibkr_trades")


PENDING = exits.stated("pending")
NO_TICKER = exits.stated("unavailable", why=FOLLOWED_NO_SUCH_TICKER)


def _tapes(**by_symbol):
    """A tape_at that answers each symbol's tape and records what was asked."""
    asked = []

    def tape_at(symbol):
        asked.append(symbol)
        return by_symbol[symbol]

    tape_at.asked = asked
    return tape_at


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    exits.reset_for_tests()
    lines.reset_for_tests()
    monkeypatch.delenv(FOLLOWED_FEED_URL_ENV, raising=False)
    monkeypatch.setattr(exits, "_path", lambda: tmp_path / "followed-exits.json")
    yield
    exits.reset_for_tests()
    lines.reset_for_tests()


# -- which reads could be glued ---------------------------------------------------------------------


@pytest.mark.parametrize("symbol, price, expected", [
    ("SOF", 114.03, ("SOFI", 14.03)),     # the bar's "SOFI 14.03": its I read as a 1 (live, 2026-10-14)
    ("XYZ", 114.03, ("XYZI", 14.03)),
    ("JBD", 18.67, ("JBDI", 8.67)),
    ("BA", 51.20, ("BAS", 1.20)),         # S read as 5
    ("AB", 812.50, ("ABB", 12.50)),       # B read as 8
    ("ABC", 10.5432, ("ABCI", 0.5432)),   # four decimals under $1
    ("XYZ", 105.20, None),                # "05.20" is no price the bar writes
    ("BAC", 50.00, None),                 # nor is 0.00
    ("JYD", 1.29, None),                  # nothing left before the point
    ("NVDL", 35.41, None),                # 3 is no letter
    ("ABCDE", 114.03, None),              # a sixth letter is no US ticker
    ("BRK.B", 112.30, None),
])
def test_unglued(symbol, price, expected):
    assert tickers.unglued(symbol, price) == expected


# -- the check -------------------------------------------------------------------------------------


def test_a_read_that_cannot_be_glued_is_not_checked():
    tape_at = _tapes()
    assert tickers.check(feed.parse_day(_day([_trade("NVDL", 35.41)]))["trades"][0], tape_at) is None
    assert tape_at.asked == []


def test_the_ticker_as_read_fitting_its_tape_is_as_read():
    tape_at = _tapes(AMD=_at(164.10))
    got = tickers.check({"symbol": "AMD", "entry_price": 164.25}, tape_at)
    assert got["state"] == "as_read" and got["other_symbol"] == "AMDI" and got["why"] is None
    assert tape_at.asked == ["AMD"]                       # the other reading is never asked for


def test_a_stable_glued_read_is_corrected_when_the_longer_ticker_fits():
    # Failure mode 1: the bar's XYZI 14.03 read as XYZ 114.03 the whole time; XYZ trades near $14, XYZI at 14.05.
    tape_at = _tapes(XYZ=_at(14.00), XYZI=_at(14.05))
    got = tickers.check({"symbol": "XYZ", "entry_price": 114.03}, tape_at)
    assert (got["state"], got["read_symbol"], got["read_price"], got["other_symbol"], got["other_price"]) == (
        "corrected", "XYZ", 114.03, "XYZI", 14.03)
    assert "XYZ 14.00" in got["why"] and "XYZI 14.05" in got["why"]


def test_neither_reading_fitting_is_unchecked():
    got = tickers.check({"symbol": "XYZ", "entry_price": 114.03}, _tapes(XYZ=_at(14.00), XYZI=_at(16.40)))
    assert got["state"] == "unchecked" and "neither fits" in got["why"]


def test_no_such_longer_ticker_means_no_glued_reading():
    # A fast stock 2% off at the entry, and "AMDI" is no ticker IBKR knows: the read is AMD, as read.
    got = tickers.check({"symbol": "AMD", "entry_price": 164.25}, _tapes(AMD=_at(161.00), AMDI=NO_TICKER))
    assert got["state"] == "as_read"


def test_a_tape_not_read_yet_is_checking():
    assert tickers.check({"symbol": "XYZ", "entry_price": 114.03}, _tapes(XYZ=PENDING))["state"] == "checking"
    got = tickers.check({"symbol": "XYZ", "entry_price": 114.03},
                        _tapes(XYZ=_at(14.0), XYZI={**PENDING, "why": "IBKR is not connected"}))
    assert got["state"] == "checking" and got["why"] == "IBKR is not connected"


def test_an_entry_window_fits_its_range_widened():
    window = exits.stated("range", low=13.90, high=14.00, from_ts=1.0, to_ts=2.0, source="ibkr_trades")
    assert tickers.fits(14.20, window) and not tickers.fits(14.30, window)
    assert tickers.fits(13.70, window) and not tickers.fits(13.60, window)
    assert not tickers.fits(14.0, exits.stated("unavailable", why="no trade"))


def test_shown_reads_every_price_back_onto_the_longer_ticker():
    trade = feed.parse_day(_day([_trade(price=114.10, adds=[("15:01:00", 114.10, 114.03)])]))["trades"][0]
    ticker = tickers.check(trade, _tapes(XYZ=_at(14.0), XYZI=_at(14.05)))
    got = tickers.shown(trade, ticker)
    assert (got["symbol"], got["entry_price"], got["price"]) == ("XYZI", 14.03, 14.10)
    assert [(a["price"], a["prev_price"]) for a in got["adds"]] == [(14.10, 14.03)]
    assert tickers.shown(trade, {**ticker, "state": "unchecked"}) is trade


# -- the day's answer --------------------------------------------------------------------------------


def _compose(trades, ticker_for, *, now_price=14.10, exit_price=13.50):
    day = feed.parse_day(_day(trades))
    priced = []

    def now_for(t):
        priced.append(t["symbol"])
        return lines.now_state("live", price=now_price, trade_ts=1.0)

    def exit_for(t):
        priced.append(t["symbol"])
        return exits.stated("at", price=exit_price, trade_ts=t["exit_ts"] - 1, to_ts=t["exit_ts"], source="ibkr_trades")

    body = view.compose(day, now=_epoch("15:00:10"), prices={"state": "live", "why": None}, now_for=now_for,
                        exit_for=exit_for, ticker_for=ticker_for)
    return body, priced


def _ticker_for(**tapes):
    return lambda t: tickers.check(t, _tapes(**tapes))


def test_the_glued_phantom_was_priced_and_is_now_corrected():
    # Before: "short XYZ at 114.03" priced at XYZ's 14.10 read +87.6%.
    before, _ = _compose([_trade()], ticker_for=None)
    assert before["traders"][0]["open"][0]["pl"]["pct"] == 87.63
    body, priced = _compose([_trade()], _ticker_for(XYZ=_at(14.0), XYZI=_at(14.05)))
    row = body["traders"][0]["open"][0]
    assert (row["symbol"], row["entry"]["first_price"], row["entry"]["avg_price"]) == ("XYZI", 14.03, 14.03)
    assert row["ticker"]["state"] == "corrected" and row["ticker"]["read_symbol"] == "XYZ"
    assert priced == ["XYZI"] and row["pl"] == {"per_share": -0.07, "pct": -0.5}
    assert row["id"] == f"ALPHA|short|XYZ|{_epoch('10:00:00'):.0f}"   # the id keeps the ticker as first read


@pytest.mark.parametrize("state, tapes", [
    ("unchecked", {"XYZ": _at(14.0), "XYZI": _at(16.4)}),
    ("checking", {"XYZ": PENDING}),
])
def test_a_ticker_not_settled_is_never_priced(state, tapes):
    body, priced = _compose([_trade(), _trade(entry_clock="14:50:00", status="closed", exit_clock="14:52:00")],
                            _ticker_for(**tapes))
    held, done = body["traders"][0]["open"][0], body["traders"][0]["closed"][0]
    assert priced == []
    assert held["ticker"]["state"] == state and held["pl"] is None
    assert held["now"]["state"] == "no_line" and held["now"]["why"] == held["ticker"]["why"]
    assert done["exit"]["state"] == ("pending" if state == "checking" else "unavailable")
    assert done["pl"] is None and done["result"] == "unscored"


def test_a_trade_the_feed_corrected_keeps_its_first_id():
    body, _ = _compose([_trade("XYZI", 14.03, read_as={"symbol": "XYZ", "price": 114.03, "until_ts": _ts("15:20:00")})],
                       _ticker_for(XYZI=_at(14.05)))
    row = body["traders"][0]["open"][0]
    assert row["symbol"] == "XYZI" and row["ticker"]["state"] == "as_read"
    assert row["id"] == f"ALPHA|short|XYZ|{_epoch('10:00:00'):.0f}"


def test_read_as_is_read_by_its_symbol_and_named_when_unreadable():
    raw = _day([_trade("XYZI", 14.03, read_as={"symbol": "XYZ", "price": 114.03, "until_ts": _ts("15:20:00")})])
    assert feed.parse_day(raw)["trades"][0]["read_as"] == "XYZ"
    raw["trades"][0]["read_as"] = {"price": 114.03}
    with pytest.raises(feed.FeedError) as err:
        feed.parse_day(raw)
    assert err.value.state == "bad_answer" and "trades[0].read_as.symbol" in err.value.message
    del raw["trades"][0]["read_as"]
    assert feed.parse_day(raw)["trades"][0]["read_as"] is None  # an older feed sends none


def test_a_record_waits_on_the_ticker_before_the_exit():
    got = feed.parse_range({"from": DATE, "to": DATE, "dates": [DATE], "trades": [
        _trade(status="closed", exit_clock="15:40:00") | {"date": DATE}]})
    body = view.records(got, span="day", now=_epoch("16:00:00"), exit_for=lambda t: pytest.fail("exit read"),
                        ticker_for=_ticker_for(XYZ=PENDING))
    assert body["pending"] == 1 and body["overall"]["unscored"] == 1


# -- the tape at the entry, through exits ------------------------------------------------------------


def test_a_ticker_ibkr_does_not_know_is_said_at_once_and_not_kept(tmp_path, monkeypatch):
    from ibkr import historical_trades

    async def unknown(symbol, end, back_sec, **_kw):
        raise historical_trades.UnknownContract(f"IBKR could not qualify {symbol}")

    monkeypatch.setattr(historical_trades, "recent_trades", unknown)
    key = ("SOFII", _epoch("14:18:56"), None)
    assert exits.view(*key, now=0.0)["state"] == "pending"
    jobs = []
    exits.pump(0.0, ibkr_ready=True, spawn=lambda name, factory: jobs.append(factory))
    asyncio.run(jobs[0]())
    got = exits.view(*key, now=1.0)
    assert got["state"] == "unavailable" and got["why"] == FOLLOWED_NO_SUCH_TICKER
    exits.pump(1_000.0, ibkr_ready=True, spawn=lambda name, factory: pytest.fail("asked again"))
    assert not (tmp_path / "followed-exits.json").exists()


# -- the route ---------------------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(FOLLOWED_FEED_URL_ENV, BASE)
    monkeypatch.setattr(routes, "_ibkr_ready", lambda: True)
    monkeypatch.setattr(routes, "_replay_desk", lambda: False)
    monkeypatch.setattr(lines, "_spawn_ib", lambda name, factory: None)
    monkeypatch.setattr(exits, "_spawn_ib", lambda name, factory: None)
    monkeypatch.setattr(lines, "_owners", lambda sym: {"followed"})
    monkeypatch.setattr(lines, "quotes", lambda syms: {s: lines.now_state("live", price=14.10, trade_ts=1.0)
                                                       for s in syms})
    monkeypatch.setattr(routes, "_read_log", lambda *_a, **_k: None)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_route_holds_no_line_until_the_ticker_is_checked_then_the_right_one(client, monkeypatch):
    today = routes.desk_day(time.time())[0]
    entry = datetime.fromisoformat(_ts("10:00:00", today)).timestamp()
    raw = _day([_trade() | {"entry_ts": _ts("10:00:00", today)}], date=today, today=today)
    monkeypatch.setattr(feed, "fetch_day", lambda base, date: feed.parse_day(copy.deepcopy(raw)))
    wanted = []
    monkeypatch.setattr(lines, "want", lambda syms, now, **_k: wanted.append(list(syms)))
    first = client.get("/api/followed-traders/day").json()["traders"][0]["open"][0]
    assert first["ticker"]["state"] == "checking" and first["pl"] is None and wanted == [[]]
    exits._finish(("XYZ", entry, None), "done", _at(14.0))      # IBKR's tape at the entry: XYZ trades near $14
    second = client.get("/api/followed-traders/day").json()["traders"][0]["open"][0]
    assert second["ticker"]["state"] == "checking" and "XYZI" in second["ticker"]["why"] and wanted[-1] == []
    exits._finish(("XYZI", entry, None), "done", _at(14.05))    # ... and XYZI at 14.05
    row = client.get("/api/followed-traders/day").json()["traders"][0]["open"][0]
    assert row["symbol"] == "XYZI" and row["ticker"]["state"] == "corrected" and wanted[-1] == ["XYZI"]
    assert row["pl"] == {"per_share": -0.07, "pct": -0.5} and row["id"] == first["id"]
    kept = json.loads((exits._path()).read_text(encoding="utf-8"))["exits"]
    assert {r["symbol"] for r in kept} == {"XYZ", "XYZI"}     # the entry's tape is kept like an exit's
