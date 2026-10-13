"""GET /api/why/{symbol} (ADR 028): the facts gathered from the desk's own caches, then the read."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import scanner_news_badge as snb
import scanner_surface
from fundamentals import _fundamentals_cache
from leaderboard import store as lb_store
from move_reason import borrow_feed, borrow_store, facts as facts_mod, routes, rules
from runtime_state import get_runtime_state

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 23, 11, 0, tzinfo=ET).timestamp()
BOARDS = ("gapper_cache", "gainer_cache", "loser_cache", "afterhours_cache", "large_cap_cache")
USA_TXT = ("#BOF|2026.09.23|10:45:00\n#SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|FIGI|\n"
           "MSS|USD|MAISON|1|X|-101.04|104.92|2000|F|\n#EOF|1\n").encode()


@pytest.fixture
def desk(monkeypatch, tmp_path):
    monkeypatch.setattr("alpaca._get_discovery_provider", lambda: "ibkr")
    monkeypatch.setattr(scanner_surface._hod_momo, "is_blocked", lambda s: False)
    monkeypatch.setattr("catalysts.live.request", lambda symbols: None)
    monkeypatch.setattr("catalysts.live.verdict_for", lambda symbol, now=None: {
        "verdict": "none_found", "sources_answered": ["alpaca", "finnhub"], "news_pending": False})
    monkeypatch.setattr("strategy.symbol_pillars.live_quote", lambda symbol: None)
    monkeypatch.setattr(facts_mod, "_read_in_background", lambda sym: None)
    monkeypatch.setenv("NOVA_BORROW_FEED", "1")
    feed = borrow_feed.BorrowFeed(fetch=lambda: USA_TXT, clock=lambda: NOW - 900,
                                  db=borrow_store.connect(tmp_path / "borrow.sqlite3"))
    feed.warm_start()
    assert feed.poll_once()
    monkeypatch.setattr(borrow_feed, "_feed", feed)
    snb.reset_for_testing()
    state = get_runtime_state()
    prev = {name: getattr(state, name) for name in BOARDS}
    for name in BOARDS:
        setattr(state, name, [])
    yield state
    for name, rows in prev.items():
        setattr(state, name, rows)
    snb.reset_for_testing()


def halts(*events):
    with lb_store.connect() as db:
        lb_store.write_batch(db, halts=[{"symbol": s, "ts": ts, "event": "start", "kind": k, "code": c, "source": src,
                                         "session_date": "2026-09-23", "recorded_ts": ts} for s, ts, k, c, src in events])


def test_a_gainer_squeezing_without_news_says_so(desk, monkeypatch):
    monkeypatch.setitem(_fundamentals_cache, "MSS", {
        "average_volume": 2_800_000.0, "float_shares": 300_081, "short_interest": 88_477, "short_ratio": 0.02,
        "last_split_factor": None, "last_split_ts": None})
    desk.gainer_cache = [{"symbol": "MSS", "price": 2.32, "change_pct": 0.487, "volume": 94_510_260}]
    halts(("MSS", NOW - 3600, "LUDP", "LUDP", "nasdaq_trade_halt_rss"),
          ("MSS", NOW - 3599, "luld", "2", "ibkr_ticker_halted"),       # the same pause seen by IBKR
          ("MSS", NOW - 1800, "LUDP", "LUDP", "nasdaq_trade_halt_rss"))

    body = routes.why("mss", NOW)

    assert (body["schema_version"], body["symbol"], body["session_date"]) == (1, "MSS", "2026-09-23")
    assert body["likely"]["kind"] == "short_squeeze"
    checks = {c["id"]: c for c in body["checks"]}
    assert checks["halts"]["value"] == "LULD pause 2x"
    assert checks["borrow"]["value"] == "Fee 104.9%/yr · 2K shares to lend"
    assert checks["reverse_split"]["value"] == "None on record"
    assert body["facts"]["float_rotation"] == pytest.approx(94_510_260 / 300_081)
    assert body["facts"]["borrow"]["open"]["fee_rate"] == 104.92


def test_a_symbol_on_no_board_with_nothing_cached_is_all_unknown(desk, monkeypatch):
    monkeypatch.setattr("catalysts.live.verdict_for", lambda symbol, now=None: None)
    body = routes.why("ZZZZ", NOW)
    checks = {c["id"]: c["state"] for c in body["checks"]}
    assert checks["news"] == checks["float"] == checks["short_interest"] == checks["reverse_split"] == "unknown"
    assert checks["borrow"] == "yes"          # the file was read, and it does not list ZZZZ: nothing to lend
    assert checks["halts"] == "no"
    assert body["likely"]["kind"] == "unexplained" and body["likely"]["confidence"] == "possible"


def test_a_failed_yahoo_read_is_unknown_not_no_split(desk, monkeypatch):
    import fundamentals

    monkeypatch.setitem(_fundamentals_cache, "FAIL", dict(fundamentals._EMPTY))
    monkeypatch.setattr(fundamentals, "fetch_failed", lambda s: s == "FAIL")
    desk.gainer_cache = [{"symbol": "FAIL", "price": 1.0, "change_pct": 0.4, "volume": 1_000}]
    checks = {c["id"]: c["state"] for c in routes.why("FAIL", NOW)["checks"]}
    assert checks["reverse_split"] == "unknown"


def test_a_stale_float_and_its_short_interest_date_reach_the_read(desk, monkeypatch):
    """#532: SECZ's 8.45M float against 163.27M shares out (12.8% insiders) is flagged on its surfaced row,
    and the short-interest check is as of FINRA's settlement date."""
    import fundamentals

    aug_31 = datetime(2026, 8, 31, tzinfo=ZoneInfo("UTC")).timestamp()
    flag, reason = fundamentals.float_credibility(8_450_000, 163_270_000, 0.128)
    monkeypatch.setitem(_fundamentals_cache, "SECZ", {
        "float_shares": 8_450_000, "shares_outstanding": 163_270_000, "held_percent_insiders": 0.128,
        "short_interest": 3_760_000, "short_interest_ts": int(aug_31), "short_ratio": 1.4,
        "float_contradicted": flag, "float_contradicted_reason": reason})
    desk.gainer_cache = [{"symbol": "SECZ", "price": 11.2, "change_pct": 0.62, "volume": 30_000_000}]

    body = routes.why("SECZ", NOW)

    assert body["facts"]["float_contradicted"] is True
    assert body["facts"]["short_interest_ts"] == aug_31
    checks = {c["id"]: c for c in body["checks"]}
    assert checks["float"]["value"] == "8.4M? shares -- low float"
    assert checks["float"]["detail"].startswith("Float 8.45M is under half of the 142.37M shares not held by insiders")
    assert checks["short_interest"]["as_of"] == aug_31


def test_the_borrow_feed_off_reads_unknown(desk, monkeypatch):
    monkeypatch.setenv("NOVA_BORROW_FEED", "0")
    checks = {c["id"]: c for c in routes.why("MSS", NOW)["checks"]}
    assert checks["borrow"]["state"] == "unknown"


def test_halts_count_one_source():
    events = [{"source": "ibkr_ticker_halted", "event": "start", "kind": "luld", "code": "2"},
              {"source": "ibkr_ticker_halted", "event": "start", "kind": "halt", "code": "T1"}]
    assert facts_mod.count_halts(events) == {"news": 1, "luld": 1, "volatility": 0, "other": 0,
                                             "source": "ibkr_ticker_halted", "carried": None}
    assert facts_mod.count_halts([]) == {"news": 0, "luld": 0, "volatility": 0, "other": 0, "source": None,
                                         "carried": None}


# -- a halt carried over from the prior exchange day (operator report 2026-10-13) ------------------------------
RSS = "nasdaq_trade_halt_rss"
FMFC_HALT = datetime(2026, 10, 12, 19, 50, tzinfo=ET).timestamp()
FMFC_RESUME = datetime(2026, 10, 13, 9, 0, tzinfo=ET).timestamp()


def _halts_check(h, now):
    return {c["id"]: c for c in rules.read({"symbol": "FMFC", "halts": h}, now)["checks"]}["halts"]


def test_a_news_halt_from_last_night_holds_the_premarket(tmp_path, monkeypatch):
    """FMFC as Nasdaq's list logged it: T1 at Oct 12 19:50, its 09:00 resumption logged at 06:19 on Oct 13. "Halts
    today" read "None today" all premarket, while the ladder read "Halted for news (T1)"."""
    monkeypatch.setenv("NOVA_LEADERBOARD_DIR", str(tmp_path / "lb"))
    with lb_store.connect() as db:
        lb_store.write_batch(db, halts=[
            {"symbol": "FMFC", "ts": FMFC_HALT, "event": "start", "kind": "T1", "code": "T1", "source": RSS,
             "session_date": "2026-10-12", "recorded_ts": FMFC_HALT + 101},
            {"symbol": "FMFC", "ts": FMFC_RESUME, "event": "end", "kind": "T3", "code": "T3", "source": RSS,
             "session_date": "2026-10-13", "recorded_ts": datetime(2026, 10, 13, 6, 19, tzinfo=ET).timestamp()}])

    seven = datetime(2026, 10, 13, 7, 0, tzinfo=ET).timestamp()
    h = facts_mod.halts_today("FMFC", seven)
    assert h["news"] == 0
    assert h["carried"] == {"kind": "news", "code": "T1", "source": RSS, "since": FMFC_HALT, "resumed": None,
                            "still_halted": True}
    assert facts_mod.halts_many(["FMFC"], seven)["FMFC"] == h
    check = _halts_check(h, seven)
    assert (check["state"], check["value"]) == ("yes", "Halted for news (T1) since Oct 12 19:50 ET, still halted")

    after = datetime(2026, 10, 13, 9, 5, tzinfo=ET).timestamp()
    h = facts_mod.halts_today("FMFC", after)
    assert h["carried"]["resumed"] == FMFC_RESUME and h["carried"]["still_halted"] is False
    assert _halts_check(h, after)["value"] == "Halted for news (T1) from Oct 12 19:50 ET to 09:00 ET"


def test_a_monday_reads_fridays_log_for_a_carried_halt():
    """MDCX: T1 at Fri Oct 9 19:50, resumed Mon Oct 12 09:00 -- the prior exchange day, not the calendar's."""
    monday = datetime(2026, 10, 12, 7, 0, tzinfo=ET).timestamp()
    assert facts_mod._halt_days(monday) == ("2026-10-12", "2026-10-09")


def test_a_halt_ended_the_prior_day_is_not_carried_and_a_missed_end_is_said():
    prior_close = datetime(2026, 10, 12, 15, 0, tzinfo=ET).timestamp()
    ended = [{"source": RSS, "event": "start", "ts": prior_close, "kind": "LUDP", "code": "LUDP"},
             {"source": RSS, "event": "end", "ts": prior_close + 300, "kind": "LUDP", "code": "LUDP"}]
    assert facts_mod.count_halts([], ended)["carried"] is None

    open_halt = [{"source": RSS, "event": "start", "ts": prior_close + 3000, "kind": "T12", "code": "T12"}]
    pause = datetime(2026, 10, 13, 9, 45, tzinfo=ET).timestamp()
    today = [{"source": RSS, "event": "start", "ts": pause, "kind": "LUDP", "code": "LUDP"}]
    h = facts_mod.count_halts(today, open_halt)
    assert (h["luld"], h["carried"]["resumed"], h["carried"]["still_halted"]) == (1, None, False)
    assert _halts_check(h, pause)["value"] == ("Halted for news (T12) since Oct 12 15:50 ET; its resumption is not "
                                               "in the log; LULD pause 1x")


# -- GET /api/why?symbols=...&board=... (the Catalyst column) ------------------------------------------------
def test_the_batch_reads_a_frozen_board_row_at_its_own_price(desk, monkeypatch):
    """GIXI 2026-10-12: the Gappers board froze at $6.08 (+56%), while the L1 line's last trade was $3.94 (+1.3%).
    The board's cell explains the row it sits in; the Trader card keeps reading the last trade."""
    monkeypatch.setitem(_fundamentals_cache, "GIXI", {"float_shares": 631_799, "short_interest": 4_041,
                                                      "short_ratio": 0.04, "last_split_factor": None})
    monkeypatch.setitem(_fundamentals_cache, "MSS", {"float_shares": 300_081, "short_interest": 88_477,
                                                     "short_ratio": 0.02, "last_split_factor": None})
    quotes = {"GIXI": {"price": 3.94, "prev_close": 3.89, "last_trade_ts": NOW - 60, "volume": 12_001_142}}
    monkeypatch.setattr("strategy.symbol_pillars.live_quote", lambda symbol: quotes.get(symbol))
    desk.gapper_cache = [{"symbol": "GIXI", "price": 6.08, "prev_close": 3.89, "change_pct": 0.563,
                          "volume": 12_000_000, "rel_volume": 139.0}]
    desk.gainer_cache = [{"symbol": "MSS", "price": 2.32, "change_pct": 0.487, "volume": 94_510_260}]
    halts(("GIXI", NOW - 3600, "LUDP", "LUDP", "nasdaq_trade_halt_rss"),
          ("MSS", NOW - 1800, "LUDP", "LUDP", "nasdaq_trade_halt_rss"))

    body = routes.why_many(["GIXI", "MSS"], board="gappers", now=NOW)

    assert (body["board"], body["replay"], body["errors"]) == ("gappers", False, {})
    gixi = body["reads"]["GIXI"]
    assert (gixi["facts"]["board"], gixi["facts"]["priced_by"], gixi["facts"]["price"]) == ("gappers", "board_row", 6.08)
    assert gixi["facts"]["change_pct"] == pytest.approx(0.563)
    assert gixi["facts"]["last_trade"] == {"price": 3.94, "change_pct": pytest.approx(3.94 / 3.89 - 1), "ts": NOW - 60}
    assert gixi["likely"]["kind"] != "not_moving" and gixi["likely"]["steps"][0]["why"] == "+56.3% today"
    assert {c["id"]: c["value"] for c in gixi["checks"]}["halts"] == "LULD pause 1x"   # one read of the log for both
    # MSS is not on Gappers: its read is the Trader card's (the first board that holds it).
    mss = body["reads"]["MSS"]
    assert (mss["facts"]["board"], mss["facts"]["priced_by"], mss["likely"]["kind"]) == ("gainers", "row", "short_squeeze")
    # The single read (the Trader card) reprices the same row by the last trade.
    card = routes.why("GIXI", NOW)
    assert (card["facts"]["priced_by"], card["facts"]["price"], card["likely"]["kind"]) == ("last_trade", 3.94, "not_moving")


def test_the_batch_refuses_what_it_cannot_read():
    from fastapi import HTTPException

    for kw in ({"symbols": " , "}, {"symbols": ",".join(f"S{i}" for i in range(81))},
               {"symbols": "MSS", "board": "watchlist"}):
        with pytest.raises(HTTPException) as err:
            routes.why_batch_route(**kw)
        assert err.value.status_code == 400


def test_one_symbols_failed_read_is_its_own(desk, monkeypatch):
    real = facts_mod.gather

    def gather(sym, now=None, board=None, halts=None):
        if sym == "BAD":
            raise RuntimeError("no row")
        return real(sym, now, board=board, halts=halts)

    monkeypatch.setattr(facts_mod, "gather", gather)
    body = routes.why_many(["BAD", "ZZZZ"], now=NOW)
    assert body["reads"]["BAD"] is None and body["errors"] == {"BAD": "RuntimeError: no row"}
    assert body["reads"]["ZZZZ"]["symbol"] == "ZZZZ"
