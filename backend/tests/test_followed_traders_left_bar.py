"""A trader who left the bar closed every trade then (operator report 2026-10-14, 13:11 ET: "why our software still
think they are holding trades?" -- NEAL's and SHAWN's show ended at 11:00 with BAC, TQQQ and AMZN on the bar, the feed
never saw those close, and the page still said Holding now with a live P/L; then the rule: "if they are off air then
all trades are closed!"). Schema: architecture/schema/followed-traders.md ("A trader who left the bar").
"""
from __future__ import annotations

import copy
import json
import time
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from followed_traders import exits, feed, lines, routes, sightings, view
from followed_traders.constants_followed import FOLLOWED_FEED_URL_ENV, FOLLOWED_LEFT_BAR_SEC

BASE = "http://127.0.0.1:8787"
DATE = "2026-10-14"


def _ts(clock: str, date: str = DATE) -> str:
    return f"{date}T{clock}-04:00"


def _epoch(clock: str, date: str = DATE) -> float:
    return datetime.fromisoformat(_ts(clock, date)).timestamp()


def _line(clock, **traders):
    return json.dumps({"clock": clock, "traders": {
        name: {"positions": pos, "unparsed": []} for name, pos in traders.items()}})


# Today's morning, as the feed read it: NEAL and SHAWN on the bar, the next show's name tags over their positions at
# 11:00:22, the next hosts' own positions at 11:05:15, then a guest segment with the bar off screen from 12:43:04.
LOG = "\n".join([
    _line("10:56:26", NEAL={"short:BAC": 49.76}, SHAWN={"long:TQQQ": 76.2, "short:AMZN": 259.47}),
    _line("10:59:24", NEAL={"short:BAC": 49.76}, SHAWN={"long:TQQQ": 76.22, "short:AMZN": 259.47}),
    _line("11:00:22", CHERIF={"short:BAC": 49.76}, JOE={"long:TQQQ": 76.22, "short:AMZN": 259.47}),
    _line("11:05:15", CHERIF={"long:TDIC": 2.17}, TJOE={}),  # JOE's name tag misread
    _line("11:30:38", CHERIF={"long:GLND": 4.16}, JOE={}),
    _line("12:43:02", CHERIF={"long:GLND": 3.81}, JOE={"long:NVDL": 34.32}),
    _line("12:43:04"),
    json.dumps({"clock": "12:44:00", "traders": {"": {"positions": {}, "unparsed": ["long:DBARBADOADAYTRADING-R"]}}}),
])
TRADERS = ["NEAL", "SHAWN", "CHERIF", "JOE"]


def _seen(log_text=LOG, latest="13:14:22"):
    return sightings.sightings(feed.parse_reads(log_text), date=DATE, traders=TRADERS, latest_clock=latest,
                               left_after_sec=FOLLOWED_LEFT_BAR_SEC)


# -- the sightings --------------------------------------------------------------------------------------------


def test_hosts_whose_show_ended_left_the_bar_and_the_next_hosts_are_only_off_screen():
    seen = _seen()
    # Last read at 10:59:24, until the next line began; the bar went on with CHERIF and JOE from 11:00:22.
    assert seen["NEAL"] == {"last_ts": _epoch("11:00:22"), "left_ts": _epoch("11:00:22")}
    assert seen["SHAWN"] == {"last_ts": _epoch("11:00:22"), "left_ts": _epoch("11:00:22")}
    # The guest segment hides the bar: nobody else is read, so they may come back to it.
    assert seen["CHERIF"] == {"last_ts": _epoch("12:43:04"), "left_ts": None}
    assert seen["JOE"] == {"last_ts": _epoch("12:43:04"), "left_ts": None}


def test_a_misread_name_tag_is_the_trader_and_an_empty_name_is_nobody():
    assert sightings.canonical("TJOE", TRADERS) == "JOE"
    assert sightings.canonical("CHERLF", TRADERS) == "CHERIF"
    assert sightings.canonical("JON", ["JOE"]) == "JON"  # a short name needs the whole name in the tag
    log = "\n".join([_line("10:00:00", NEAL={}, JOE={}), _line("10:00:02", TJOE={}),
                     _line("10:00:04", NEAL={}, TJOE={})])
    # JOE read as TJOE is still JOE; nobody but NEAL and JOE was read, so neither left.
    assert _seen(log, latest="10:30:00")["JOE"] == {"last_ts": _epoch("10:30:00"), "left_ts": None}
    assert "SHAWN" not in _seen(log, latest="10:30:00")  # never read: no sighting, no claim


def test_a_departure_counts_only_once_the_bar_has_gone_on_without_them_for_a_minute():
    log = "\n".join([_line("10:00:00", NEAL={"short:BAC": 49.76}, SHAWN={}), _line("10:00:30", SHAWN={})])
    assert _seen(log, latest="10:01:00")["NEAL"]["left_ts"] is None  # 30 s: a name tag misread for a few frames
    assert _seen(log, latest="10:01:30")["NEAL"]["left_ts"] == _epoch("10:00:30")


def test_a_trader_back_on_the_bar_has_not_left():
    log = LOG + "\n" + _line("14:00:00", NEAL={}, SHAWN={})
    seen = _seen(log, latest="14:00:02")
    assert seen["NEAL"] == {"last_ts": _epoch("14:00:02"), "left_ts": None}


def test_a_new_host_standing_in_is_their_own_trader_and_the_regular_left():
    # Operator, 2026-10-14: "they may change the actors ... maybe neal is going to be sick and be replaced with someone
    # else." No name is fixed: MARK, with no trade yet, is someone else on the bar all the same.
    log = "\n".join([_line("09:30:00", NEAL={"short:BAC": 49.76}, SHAWN={}),
                     _line("09:45:00", MARK={}, SHAWN={"long:TQQQ": 76.2})])
    seen = sightings.sightings(feed.parse_reads(log), date=DATE, traders=["NEAL", "SHAWN"], latest_clock="09:50:00",
                               left_after_sec=FOLLOWED_LEFT_BAR_SEC)
    assert seen["NEAL"]["left_ts"] == _epoch("09:45:00") and seen["SHAWN"]["left_ts"] is None
    # Once MARK trades, MARK is a trader of the day like any other.
    log += "\n" + _line("09:50:00", MARK={"long:TSLA": 250.0}, SHAWN={"long:TQQQ": 76.2})
    seen = sightings.sightings(feed.parse_reads(log), date=DATE, traders=["NEAL", "SHAWN", "MARK"],
                               latest_clock="09:55:00", left_after_sec=FOLLOWED_LEFT_BAR_SEC)
    assert seen["MARK"] == {"last_ts": _epoch("09:55:00"), "left_ts": None}


def test_a_regular_who_never_came_on_has_no_sighting():
    log = _line("09:30:00", MARK={}, SHAWN={})
    seen = sightings.sightings(feed.parse_reads(log), date=DATE, traders=["NEAL", "SHAWN", "MARK"],
                               latest_clock="09:50:00", left_after_sec=FOLLOWED_LEFT_BAR_SEC)
    assert "NEAL" not in seen and seen["MARK"]["left_ts"] is None


def test_a_past_day_measures_by_its_own_newest_read():
    seen = sightings.sightings(feed.parse_reads(LOG), date=DATE, traders=TRADERS, latest_clock=None,
                               left_after_sec=FOLLOWED_LEFT_BAR_SEC)
    assert seen["NEAL"]["left_ts"] == _epoch("11:00:22") and seen["CHERIF"]["left_ts"] is None


# -- the day's answer ---------------------------------------------------------------------------------------


def _trade(trader, side, symbol, price, entry_clock):
    return {"trader": trader, "side": side, "symbol": symbol, "entry_price": price, "price": price,
            "entry_ts": _ts(entry_clock), "entry_since_ts": None, "entry_known": True, "adds": [],
            "exit_ts": None, "exit_since_ts": None, "status": "open",
            "entry_evidence": None, "exit_evidence": None}


def _raw_day(date=DATE):
    status = {"video": {"id": "YvrqOmwbAgY", "title": "Afternoon show"}, "live": True, "clock": "13:14:22",
              "updated_at": _ts("13:14:24", date), "bar_visible": False, "traders": [],
              "positions": {"NEAL": {"short:BAC": 49.76}, "CHERIF": {"long:GLND": 3.81}}}
    return {"date": date, "today": date, "dates": [date], "status": status,
            "trades": [_trade("NEAL", "short", "BAC", 49.76, "10:27:02"),
                       _trade("CHERIF", "long", "GLND", 3.81, "11:30:38")]}


def test_a_trader_who_left_the_bar_closed_every_trade_when_they_left():
    day = feed.parse_day(_raw_day())
    exits_asked = []

    def exit_for(t):
        exits_asked.append((t["symbol"], t["exit_ts"], t["exit_since_ts"]))
        return {"state": "at", "price": 50.0, "low": None, "high": None, "from_ts": None, "to_ts": t["exit_ts"],
                "trade_ts": t["exit_ts"] - 1, "source": "ibkr_trades", "why": None}

    body = view.compose(day, now=_epoch("13:14:30"), prices={"state": "live", "why": None},
                        now_for=lambda t: lines.now_state("live", price=50.72, trade_ts=1.0),
                        exit_for=exit_for, seen=_seen())
    neal, cherif = body["traders"]
    assert neal["seen"]["left_ts"] == _epoch("11:00:22") and neal["open"] == []
    bac = neal["closed"][0]
    # Closed when they left, priced by IBKR's tape like any exit, and said to be a close on leaving.
    assert bac["status"] == "closed" and bac["left_bar"] is True
    assert exits_asked == [("BAC", _epoch("11:00:22"), None)]  # last seen and left at the same read: one second
    assert bac["pl"] == {"per_share": -0.24, "pct": -0.48} and bac["result"] == "loss"
    assert bac["held"] == {"min_sec": round(_epoch("11:00:22") - _epoch("10:27:02")),
                           "max_sec": round(_epoch("11:00:22") - _epoch("10:27:02"))}
    assert bac["evidence"]["exit"] is None  # no close was seen, so no exit image
    assert neal["record"]["open"] == 0 and neal["record"]["losses"] == 1
    # Off screen but not gone (a guest segment): still open, priced as before.
    glnd = cherif["open"][0]
    assert glnd["now"]["state"] == "live" and glnd["left_bar"] is False and cherif["seen"]["left_ts"] is None


def test_a_bar_unread_before_the_others_came_on_is_an_exit_window():
    log = "\n".join([_line("10:00:00", NEAL={"short:BAC": 49.76}, SHAWN={}), _line("10:00:10"),
                     _line("10:05:00", SHAWN={})])
    gone = _seen(log, latest="10:07:00")["NEAL"]
    trade = feed.parse_day(_raw_day())["trades"][0]
    closed = view.closed_on_leaving(trade, gone)
    assert (closed["exit_since_ts"], closed["exit_ts"]) == (_epoch("10:00:10"), _epoch("10:05:00"))
    # A trade the feed already closed, or a trader still on the bar, is as the feed has it.
    assert view.closed_on_leaving(trade, None) is trade
    done = {**trade, "status": "closed", "exit_ts": _epoch("10:30:00")}
    assert view.closed_on_leaving(done, gone) is done


def _unread():
    return json.dumps({"clock": None, "traders": {}})


def test_the_line_after_frames_the_feed_could_not_read_says_so():
    log = feed.parse_reads("\n".join([
        _line("10:00:00", ALPHA={}), _unread(), _line("10:00:05", ALPHA={}),
        json.dumps({"clock": "10:00:97", "traders": {}}), _line("10:00:09", ALPHA={}), _line("10:00:11", ALPHA={})]))
    assert [(line["clock"], line.get("unread_before", False)) for line in log] == [
        ("10:00:00", False), ("10:00:05", True), ("10:00:09", True), ("10:00:11", False)]


def test_a_host_gone_after_a_stretch_the_feed_could_not_read_left_somewhere_in_it():
    # 2026-10-15: the feed restarted at 10:55 onto a stream it could not read (one clock-less line), came back at 11:04
    # on the next show, and Nova priced every position the morning's hosts still held at 11:04:37, ten minutes after
    # they were last seen. When they left is only known to be after their last line.
    log = "\n".join([_line("10:54:26", ALPHA={"short:QRST": 14.3}, BRAVO={"long:WXYZ": 344.55}), _unread(),
                     _line("11:04:37", CHARLIE={"long:MNOP": 6.5}, DELTA={})])
    seen = sightings.sightings(feed.parse_reads(log), date=DATE, traders=["ALPHA", "BRAVO", "CHARLIE"],
                               latest_clock="11:10:00", left_after_sec=FOLLOWED_LEFT_BAR_SEC)
    assert seen["ALPHA"] == {"last_ts": _epoch("10:54:26"), "left_ts": _epoch("11:04:37")}
    trade = {**_trade("ALPHA", "short", "QRST", 14.3, "10:15:59"), "entry_ts": _epoch("10:15:59")}
    closed = view.closed_on_leaving(trade, seen["ALPHA"])
    assert (closed["exit_since_ts"], closed["exit_ts"]) == (_epoch("10:54:26"), _epoch("11:04:37"))
    # Priced as a window (IBKR's low and high in it), so it is unscored, never a loss at the moment the feed came back.
    row = view.trade_row(closed, DATE, now=_epoch("11:10:00"), prices={"state": "live", "why": None},
                         now_for=lambda t: lines.now_state("off"),
                         exit_for=lambda t: exits.stated("range", low=14.2, high=14.55, from_ts=t["exit_since_ts"],
                                                         to_ts=t["exit_ts"], source="ibkr_1min_bars"))
    assert row["exit"]["state"] == "range" and row["result"] == "unscored"
    assert row["pl"] == {"low_per_share": -0.25, "high_per_share": 0.1, "low_pct": -1.75, "high_pct": 0.7}


def test_a_frame_the_feed_could_not_read_while_the_host_stayed_on_changes_nothing():
    log = "\n".join([_line("10:00:00", ALPHA={"short:QRST": 14.3}), _unread(),
                     _line("10:00:03", ALPHA={"short:QRST": 14.3}), _line("10:40:00", CHARLIE={})])
    seen = sightings.sightings(feed.parse_reads(log), date=DATE, traders=["ALPHA", "CHARLIE"], latest_clock="10:45:00",
                               left_after_sec=FOLLOWED_LEFT_BAR_SEC)
    # Read again after the blank frame, so they were on the bar until the next line, as before: one exit second.
    assert seen["ALPHA"] == {"last_ts": _epoch("10:40:00"), "left_ts": _epoch("10:40:00")}


def test_without_a_read_log_the_day_reads_as_before():
    day = feed.parse_day(_raw_day())
    body = view.compose(day, now=_epoch("13:14:30"), prices={"state": "live", "why": None},
                        now_for=lambda t: lines.now_state("live", price=50.72, trade_ts=1.0), exit_for=lambda t: {})
    assert [t["seen"] for t in body["traders"]] == [None, None]
    assert body["traders"][0]["open"][0]["now"]["state"] == "live"


# -- the route ------------------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    exits.reset_for_tests()
    lines.reset_for_tests()
    monkeypatch.delenv(FOLLOWED_FEED_URL_ENV, raising=False)
    monkeypatch.setattr(exits, "_path", lambda: tmp_path / "followed-exits.json")
    monkeypatch.setattr(routes, "_log_cache", {})
    yield
    exits.reset_for_tests()
    lines.reset_for_tests()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(FOLLOWED_FEED_URL_ENV, BASE)
    monkeypatch.setattr(routes, "_ibkr_ready", lambda: True)
    monkeypatch.setattr(routes, "_replay_desk", lambda: False)
    monkeypatch.setattr(lines, "_spawn_ib", lambda name, factory: None)
    monkeypatch.setattr(exits, "_spawn_ib", lambda name, factory: None)
    monkeypatch.setattr(lines, "quotes", lambda syms: {s: lines.now_state("live", price=2.5, trade_ts=1.0)
                                                       for s in syms})
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def _serve_today(monkeypatch):
    today = routes.desk_day(time.time())[0]
    raw = _raw_day(today)
    monkeypatch.setattr(feed, "fetch_day", lambda base, date: feed.parse_day(copy.deepcopy(raw)))
    asked = []

    def fetch_reads(base, date):  # the same reads, placed on the desk's today
        asked.append(date)
        return feed.parse_reads(LOG)

    monkeypatch.setattr(feed, "fetch_reads", fetch_reads)
    return today, asked


def test_route_closes_the_trades_of_a_trader_who_left_and_holds_no_line_for_them(client, monkeypatch):
    today, asked = _serve_today(monkeypatch)
    wanted = []
    monkeypatch.setattr(lines, "want", lambda syms, now: wanted.append(syms))
    body = client.get("/api/followed-traders/day").json()
    neal = next(t for t in body["traders"] if t["name"] == "NEAL")
    assert neal["open"] == [] and neal["closed"][0]["left_bar"] is True and neal["seen"]["left_ts"] is not None
    assert neal["closed"][0]["exit"]["state"] == "pending"  # IBKR's tape at the exit is read in the background
    assert wanted == [["GLND"]] and asked == [today]
    # Asked again within FOLLOWED_SEEN_CACHE_SEC (the toasts' read too): the log is not asked of the feed again.
    quiet = client.get("/api/followed-traders/day?quotes=0").json()
    assert next(t for t in quiet["traders"] if t["name"] == "NEAL")["closed"][0]["left_bar"] is True
    assert asked == [today]


def test_route_record_counts_a_trade_closed_on_leaving_and_keeps_a_finished_days_log(client, monkeypatch):
    def trades(base, start, end):
        raw = _raw_day()
        return feed.parse_range({"from": start, "to": end, "dates": [DATE],
                                 "trades": [t | {"date": DATE} for t in raw["trades"]]})

    asked = []

    def fetch_reads(base, date):
        asked.append(date)
        return feed.parse_reads(LOG)

    monkeypatch.setattr(feed, "fetch_trades", trades)
    monkeypatch.setattr(feed, "fetch_reads", fetch_reads)
    body = client.get(f"/api/followed-traders/record?range=all&date={DATE}").json()
    records = {t["name"]: t["record"] for t in body["traders"]}
    assert records["NEAL"]["open"] == 0 and records["NEAL"]["unscored"] == 1  # its exit is read in the background
    assert records["CHERIF"]["open"] == 1
    client.get(f"/api/followed-traders/record?range=all&date={DATE}")
    assert asked == [DATE]  # a day before the desk's today is finished: its log is asked once


def test_a_read_log_the_feed_cannot_give_is_no_sighting(monkeypatch, caplog):
    def broken(base, date):
        raise feed.FeedError("bad_answer", "reads.jsonl line 3 is not JSON")

    monkeypatch.setattr(feed, "fetch_reads", broken)
    assert routes._read_log(BASE, DATE, 1000.0) is None
    assert "could not be read" in caplog.text
    caplog.clear()
    monkeypatch.setattr(routes, "_log_cache", {})

    def missing(base, date):
        raise feed.FeedError("missing", "HTTP 404")

    monkeypatch.setattr(feed, "fetch_reads", missing)
    assert routes._read_log(BASE, DATE, 1000.0) is None
    assert caplog.text == ""  # a feed that keeps no log for the day is not a fault
